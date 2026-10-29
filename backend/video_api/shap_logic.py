"""
SHAP-вычисления и группировка факторов (Video API, вариант A).

Сюда вынесены: восстановление вектора признаков от Streamlit, расчёт
SHAP-значений, разбиение по смысловым группам и вспомогательные
функции для отчёта «фактор -> длительность».
"""

from typing import Any

import numpy as np
import pandas as pd
from video_api.config import FACTOR_DURATION_S, GROUP_VALUE_LABELS, GROUPS, OVERALL_DUR_S
from video_api.models import FEATURE_NAMES, explainer, model


def _try_load_feature_frame(payload: dict[str, Any]) -> pd.DataFrame:
    """Преобразует словарь признаков от Streamlit в DataFrame нужной структуры."""
    frame = pd.DataFrame([payload])
    # Гарантируем нужный порядок и полноту колонок.
    if FEATURE_NAMES:
        frame = frame.reindex(columns=FEATURE_NAMES, fill_value=0)
    frame = frame.fillna(0)
    # Убеждаемся, что значения числовые.
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)
    return frame


def compute_shap_top_factors(feature_frame: pd.DataFrame) -> list[str]:
    """Возвращает упорядоченный список имён признаков по |SHAP| (top first)."""
    return [name for name, _ in compute_shap_with_magnitudes(feature_frame)]


def compute_shap_with_magnitudes(feature_frame: pd.DataFrame) -> list:
    """Возвращает список кортежей (имя_признака, |SHAP|-значение), top first."""
    if explainer is None:
        return []
    explanation = explainer(feature_frame)
    shap_vals = np.asarray(explanation.values)

    if shap_vals.ndim == 3:
        # multiclass: берём значения для предсказанного класса
        pred_class = int(model.predict(feature_frame)[0])
        shap_vals = shap_vals[0, :, pred_class]
    else:
        shap_vals = shap_vals[0]

    names = list(feature_frame.columns)
    order = np.argsort(-np.abs(shap_vals))
    result = []
    for i in order:
        mag = abs(float(shap_vals[i]))
        # Отбрасываем нулевые вклады
        if mag > 1e-9:
            result.append((names[i], mag))
    return result


def shap_map(feature_frame: pd.DataFrame) -> dict[str, float]:
    """Словарь {имя_признака: |SHAP|} для всех признаков (для группировки)."""
    if explainer is None:
        return {}
    return {name: mag for name, mag in compute_shap_with_magnitudes(feature_frame)}


def _chosen_feature_name(frame: pd.DataFrame, prefixes) -> str | None:
    """Имя признака со значением 1 среди заданных префиксов (выбор клиента)."""
    for prefix in prefixes:
        if prefix is None:
            continue
        for col in frame.columns:
            if col.startswith(prefix) and int(frame.iloc[0][col]) == 1:
                return col
    return None


def _dedupe_chosen_groups(feature_names: list[str]) -> list[str]:
    """Оставляет ТОЛЬКО ПЕРВОГО представителя каждой смысловой группы."""
    seen: set = set()
    result: list[str] = []
    for name in feature_names:
        g = _group_key_of(name)
        if g is None:
            result.append(name)
            continue
        if g in seen:
            continue
        seen.add(g)
        result.append(name)
    return result


def _group_key_of(name: str) -> str | None:
    """Ключ смысловой группы признака (flat_plan/priorities/finishing/children)."""
    for grp in GROUPS:
        cp = grp.get("clip_prefix")
        ap = grp.get("alt_prefix")
        if (cp and name.startswith(cp)) or (ap and name.startswith(ap)):
            return grp["key"]
    return None


def compute_group_shap(feature_frame: pd.DataFrame) -> list[dict]:
    """Считает SHAP по ГРУППАМ и возвращает упорядоченные по |SHAP| строки.

    Для каждой группы вычисляет:
      - sum_shap       — сумма модулей SHAP по признакам группы;
      - chosen_feature — имя признака, которое выбрал клиент (==1);
      - chosen_shap    — |SHAP| выбранного варианта;
      - max_feature    — признак с максимальным |SHAP| внутри группы;
      - is_max         — True, если выбранный вариант и есть макс. по группе.
    Порядок: по убыванию sum_shap."""
    smap = shap_map(feature_frame)
    rows = []
    for g in GROUPS:
        members = []
        for col in feature_frame.columns:
            if col.startswith(g["prefix"]) or (
                g.get("alt_prefix") and col.startswith(g["alt_prefix"])
            ):
                members.append(col)
        # Признаки без |SHAP| (нулевой вклад) в сумму группы не входят.
        sum_shap = sum(smap.get(col, 0.0) for col in members)

        chosen = _chosen_feature_name(feature_frame, [g["clip_prefix"], g["alt_prefix"]])
        chosen_shap = abs(float(smap.get(chosen, 0.0) or 0.0)) if chosen else 0.0

        max_feature = chosen
        max_shap = chosen_shap
        for col in members:
            m = smap.get(col, 0.0)
            if m > max_shap:
                max_shap = m
                max_feature = col

        is_max = (
            bool(chosen) and (chosen == max_feature) or (chosen is None and max_feature is None)
        )
        rows.append(
            {
                "key": g["key"],
                "label": g["label"],
                "sum_shap": float(sum_shap),
                "chosen_feature": chosen,
                "chosen_shap": float(chosen_shap),
                "max_feature": max_feature,
                "max_shap": float(max_shap),
                "is_max": bool(is_max),
            }
        )
    rows.sort(key=lambda r: -r["sum_shap"])
    return rows


def group_label_for_chosen(group_row: dict) -> str:
    """Читаемая подпись группы + выбранный клиентом вариант."""
    chosen = group_row.get("chosen_feature")
    if not chosen:
        return group_row["label"]
    # Находим clip-префикс группы, чтобы отрезать его от имени признака.
    clip_prefix = None
    for g in GROUPS:
        if g["key"] == group_row["key"]:
            clip_prefix = g.get("clip_prefix")
            break
    if clip_prefix and chosen.startswith(clip_prefix):
        tail = chosen[len(clip_prefix) :].lstrip("_")
    else:
        mid = chosen.split("__", 1)[1] if "__" in chosen else chosen
        tail = mid.rsplit("_", 1)[-1] if "_" in mid else mid
    readable = GROUP_VALUE_LABELS.get(tail, tail)
    return f'{group_row["label"]}: {readable}'


def _factor_duration(name: str) -> int:
    for prefix, dur in FACTOR_DURATION_S.items():
        if str(name).startswith(prefix):
            return dur
    return OVERALL_DUR_S


def _factor_report(feature_frame, ranked_factors) -> list[dict]:
    """Отчёт по факторам: длительность пропорциональна вкладу фактора
    (|SHAP|), как заказано: чем больше вклад — тем большая длительность.
    Номинальная длина готового ролика — ROLL_SEC секунд."""
    smap = shap_map(feature_frame)
    ROLL_SEC = 30
    items = []
    for f in ranked_factors or []:
        items.append(
            {
                "factor": str(f),
                "shap_value": round(float(smap.get(f, 0.0) or 0.0), 4),
            }
        )
    total_shap = sum(v["shap_value"] for v in items) or 1.0
    for v in items:
        share = v["shap_value"] / total_shap
        v["duration_s"] = max(1, round(share * ROLL_SEC))
    return items
