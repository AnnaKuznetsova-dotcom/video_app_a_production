"""Сборка вектора признаков (аналог блокнота) + локальная модель:
«Сравнение с ближайшим конкурентом» и знаковый SHAP по группам
(та же global_best_model.joblib, что и в бэкенде; алгоритм не меняется)."""

import os

import numpy as np
import pandas as pd
import streamlit as st
from videoapp.questionnaire import (
    ANSWER_FRAGMENT_MAP,
    AREA_QUESTION,
    CROSS_MAP,
    EXTRA_GROUP_ANSWERS,
    QUESTIONNAIRE_MAP,
)
from videoapp.settings import FEATURES_PATH, MODEL_PATH, SETTLEMENT_NAMES


# ---------------------------------------------------------------------------
# ЛОГИКА СБОРКИ ВЕКТОРА (аналог блокнота)
# ---------------------------------------------------------------------------
@st.cache_data
def load_feature_names() -> list[str]:
    if not os.path.exists(FEATURES_PATH):
        raise FileNotFoundError(f"Не найден {FEATURES_PATH}.")
    with open(FEATURES_PATH, encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]
    return names


def build_feature_vector(ans: dict[str, str], area: float | None) -> dict[str, int]:
    # area_to_rank обязана быть определена в app.py (контракт тестов
    # app.area_to_rank); импортируем лениво, чтобы не зациклить
    # app → videoapp → app.
    from app import area_to_rank  # noqa: PLC0415

    feature_names = load_feature_names()
    vector: dict[str, int] = {}

    def reset(prefix: str):
        for col in feature_names:
            if col.startswith(prefix):
                vector[col] = 0

    def set_flag(prefix: str, value_part: str):
        frag = ANSWER_FRAGMENT_MAP.get(prefix, {}).get(value_part)
        if frag is not None:
            target = f"{prefix}_{frag}"
            if target in feature_names:
                vector[target] = 1
                return
        for col in feature_names:
            if col.startswith(prefix) and value_part in col and vector.get(col) == 0:
                vector[col] = 1

    for item in QUESTIONNAIRE_MAP:
        prefix = item["feature_prefix"]
        reset(prefix)
        sel = ans.get(prefix)
        if sel:
            set_flag(prefix, sel)
        extra = EXTRA_GROUP_ANSWERS.get(prefix)
        if extra:
            set_flag(prefix, extra)

    for rule in CROSS_MAP:
        sel = ans.get(rule["source_prefix"])
        if not sel:
            continue
        target_val = rule["mapping"].get(sel)
        if target_val:
            reset(rule["target_prefix"])
            set_flag(rule["target_prefix"], target_val)

    reset(AREA_QUESTION["column_name"])
    if area is not None:
        vector[AREA_QUESTION["column_name"]] = area_to_rank(area)

    return {col: int(vector.get(col, 0)) for col in feature_names}


# ---------------------------------------------------------------------------
# ЛОКАЛЬНАЯ МОДЕЛЬ
# ---------------------------------------------------------------------------
CLASS_MAP = {
    0: "Kaskad_Park",
    1: "Akademia_Park",
    2: "Fedoskino_Park",
    3: "Park_Aprel",
}

GROUP_DEFS = [
    {
        "key": "flat_plan",
        "label": "Планировка",
        "prefix": "bin_num__квартира_планировка",
        "alt_prefix": "few_cat__количество_комнат",
    },
    {"key": "priorities", "label": "Приоритеты", "prefix": "bin_num__приоритеты"},
    {"key": "finishing", "label": "Отделка", "prefix": "bin_num__отделка"},
    {"key": "children", "label": "Дети", "prefix": "few_cat__есть_ли_дети"},
]


@st.cache_resource
def load_model_pack():
    import joblib
    import shap

    model = joblib.load(MODEL_PATH)
    clf = model
    if hasattr(model, "named_steps") and len(model.named_steps) > 0:
        clf = list(model.named_steps.values())[-1]
    elif hasattr(model, "steps") and len(model.steps) > 0:
        clf = model.steps[-1][1]
    explainer = shap.TreeExplainer(clf)
    feat_names = list(getattr(clf, "feature_names_in_", [])) or load_feature_names()
    return model, explainer, feat_names


def _model_frame(vector: dict[str, int]) -> pd.DataFrame:
    _, _, feat_names = load_model_pack()
    frame = pd.DataFrame([vector]).reindex(columns=feat_names, fill_value=0)
    return frame.apply(pd.to_numeric, errors="coerce").fillna(0)


def _group_signed_shap(sv, columns: list[str]) -> list[dict]:
    rows = []
    for g in GROUP_DEFS:
        signed, magnitude = 0.0, 0.0
        for name, val in zip(columns, sv, strict=False):
            if name.startswith(g["prefix"]) or (
                g.get("alt_prefix") and name.startswith(g["alt_prefix"])
            ):
                signed += float(val)
                magnitude += abs(float(val))
        rows.append(
            {"key": g["key"], "label": g["label"], "signed": signed, "magnitude": magnitude}
        )
    return rows


def compute_compare(vector: dict[str, int]) -> dict | None:
    """Победитель + ближайший конкурент (2-й класс по вероятности), знаковый
    SHAP по группам для обоих классов. Возвращает None, если модель недоступна."""
    try:
        model, explainer, _ = load_model_pack()
        frame = _model_frame(vector)
        probs = np.asarray(model.predict_proba(frame)[0])
        order = list(np.argsort(-probs))
        explanation = explainer(frame)
        sv = np.asarray(explanation.values)
        if sv.ndim == 3:
            sv_win, sv_run = sv[0, :, order[0]], sv[0, :, order[1]]
        else:
            sv_win, sv_run = sv[0], sv[0]
        winner = CLASS_MAP.get(int(order[0]), str(order[0]))
        runner = CLASS_MAP.get(int(order[1]), str(order[1]))
        return {
            "winner": winner,
            "runner": runner,
            "winner_label": SETTLEMENT_NAMES.get(winner, winner),
            "runner_label": SETTLEMENT_NAMES.get(runner, runner),
            "rows_win": _group_signed_shap(sv_win, list(frame.columns)),
            "rows_run": _group_signed_shap(sv_run, list(frame.columns)),
        }
    except Exception:
        return None


def local_signed_group_shap(vector: dict[str, int], klass: int | None = None) -> list[dict] | None:
    """Знаковый SHAP по группам для класса winner (для «Факторного анализа»)."""
    try:
        model, explainer, _ = load_model_pack()
        frame = _model_frame(vector)
        if klass is None:
            klass = int(model.predict(frame)[0])
        explanation = explainer(frame)
        sv = np.asarray(explanation.values)
        sv = sv[0, :, klass] if sv.ndim == 3 else sv[0]
        return _group_signed_shap(sv, list(frame.columns))
    except Exception:
        return None
