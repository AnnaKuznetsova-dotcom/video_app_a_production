"""Сборка вектора признаков из ответов анкеты (feature generation, этап фронтенда).

Аналог блокнота: обнуление группы → единица выбранного значения → перенос
между группами → ранг площади. Вектор передаётся в backend /generate/ и
не содержит SHAP/объяснений: сервис выдаёт фиксированный ролик посёлка.
"""

import os

import streamlit as st
from videoapp.questionnaire import (
    ANSWER_FRAGMENT_MAP,
    AREA_QUESTION,
    CROSS_MAP,
    EXTRA_GROUP_ANSWERS,
    QUESTIONNAIRE_MAP,
)
from videoapp.settings import FEATURES_PATH


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


def _reset_prefix(vector: dict[str, int], feature_names: list[str], prefix: str) -> None:
    """Обнуляет все колонки группы (one-hot внутри группы может быть 0/0/…)."""
    for col in feature_names:
        if col.startswith(prefix):
            vector[col] = 0


def _set_flag(
    vector: dict[str, int], feature_names: list[str], prefix: str, value_part: str
) -> None:
    """Ставит 1 в колонку `<prefix>_<фрагмент>` (или по подстроке-совпадению)."""
    frag = ANSWER_FRAGMENT_MAP.get(prefix, {}).get(value_part)
    if frag is not None:
        target = f"{prefix}_{frag}"
        if target in feature_names:
            vector[target] = 1
            return
    for col in feature_names:
        if col.startswith(prefix) and value_part in col and vector.get(col) == 0:
            vector[col] = 1


def _apply_questionnaire(
    vector: dict[str, int], feature_names: list[str], ans: dict[str, str]
) -> None:
    """Одна запись на каждую группу анкеты (с учётом «дополнительных» ответов)."""
    for item in QUESTIONNAIRE_MAP:
        prefix = item["feature_prefix"]
        _reset_prefix(vector, feature_names, prefix)
        sel = ans.get(prefix)
        if sel:
            _set_flag(vector, feature_names, prefix, sel)
        extra = EXTRA_GROUP_ANSWERS.get(prefix)
        if extra:
            _set_flag(vector, feature_names, prefix, extra)


def _apply_cross_rules(
    vector: dict[str, int], feature_names: list[str], ans: dict[str, str]
) -> None:
    """Переносы между группами (CROSS_MAP: например, «ипотека» → «схема_ипотека»)."""
    for rule in CROSS_MAP:
        sel = ans.get(rule["source_prefix"])
        if not sel:
            continue
        target_val = rule["mapping"].get(sel)
        if target_val:
            _reset_prefix(vector, feature_names, rule["target_prefix"])
            _set_flag(vector, feature_names, rule["target_prefix"], target_val)


def build_feature_vector(ans: dict[str, str], area: float | None) -> dict[str, int]:
    """Ответы анкеты → полный вектор признаков модели (все колонки, нули/единицы)."""
    # area_to_rank обязана быть определена в app.py (контракт тестов
    # app.area_to_rank); импортируем лениво, чтобы не зациклить
    # app → videoapp → app.
    from app import area_to_rank  # noqa: PLC0415

    feature_names = load_feature_names()
    vector: dict[str, int] = {}

    _apply_questionnaire(vector, feature_names, ans)
    _apply_cross_rules(vector, feature_names, ans)

    area_col = AREA_QUESTION["column_name"]
    _reset_prefix(vector, feature_names, area_col)
    if area is not None:
        vector[area_col] = area_to_rank(area)

    return {col: int(vector.get(col, 0)) for col in feature_names}
