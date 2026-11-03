"""Юнит-тесты этапов data preprocessing и feature generation.

Проверяем:
  - `data_preprocessing.load_feature_names` — чтение списка признаков модели
    (контейнерный путь, локальный fallback);
  - `data_preprocessing.load_feature_frame` — вектор из JSON → DataFrame
    строго по колонкам модели (reindex, числовые значения, пропуски = 0);
  - `feature_generation.validate_feature_dict` — известные/лишние ключи и
    покрытие групп анкеты.
"""

import os
import sys

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BACKEND = os.path.join(_ROOT, "backend")
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pipeline import data_preprocessing as dp  # noqa: E402
from pipeline.feature_generation import validate_feature_dict  # noqa: E402

REPO_FEATURES_PATH = os.path.join(_BACKEND, "data", "feature_names.txt")


@pytest.fixture(scope="module")
def feature_names():
    names = dp.load_feature_names(REPO_FEATURES_PATH)
    return names


# ---------------------------------------------------------------------------
# load_feature_names
# ---------------------------------------------------------------------------
def test_load_feature_names_from_repo_file(feature_names):
    assert len(feature_names) == 42
    assert feature_names[0] == "bin_num__квартира_планировка_1_комн"


def test_load_feature_names_local_fallback(monkeypatch, feature_names):
    """Контейнерного пути нет — берётся локальный fallback из репозитория."""
    monkeypatch.setenv("FEATURE_NAMES_PATH", "")
    loaded = dp.load_feature_names()
    assert loaded == feature_names


# ---------------------------------------------------------------------------
# load_feature_frame — вектор признаков → DataFrame модели
# ---------------------------------------------------------------------------
def test_frame_has_all_model_columns(feature_names):
    partial = {feature_names[1]: 1}  # прислано только одно значение
    frame = dp.load_feature_frame(partial)
    assert list(frame.columns) == feature_names
    assert len(frame) == 1
    assert frame[feature_names[1]].iloc[0] == 1
    assert frame[feature_names[0]].iloc[0] == 0  # остальные — нули


def test_frame_numeric_and_no_missing(feature_names):
    dirty = {feature_names[0]: "abc", feature_names[1]: float("nan"), feature_names[2]: True}
    frame = dp.load_feature_frame(dirty)
    assert pd.api.types.is_numeric_dtype(frame[feature_names[0]])
    assert frame[feature_names[0]].iloc[0] == 0  # битая строка → 0
    assert frame[feature_names[1]].iloc[0] == 0  # NaN → 0
    assert frame[feature_names[2]].iloc[0] == 1  # True → 1


def test_frame_order_matches_feature_names(feature_names):
    reversed_vector = {name: idx for idx, name in enumerate(reversed(feature_names))}
    frame = dp.load_feature_frame(reversed_vector)
    assert list(frame.columns) == feature_names


def test_try_load_feature_frame_alias():
    assert dp._try_load_feature_frame is dp.load_feature_frame


# ---------------------------------------------------------------------------
# validate_feature_dict (feature generation)
# ---------------------------------------------------------------------------
def test_validate_known_and_unknown_keys(feature_names):
    vector = {feature_names[0]: 1, "неизвестный__ключ": 1}
    report = validate_feature_dict(vector)
    assert feature_names[0] in report["known_keys"]
    assert report["unknown_keys"] == ["неизвестный__ключ"]


def test_validate_groups_coverage(feature_names):
    prefix = "bin_num__квартира_планировка"
    hit_col = next(c for c in feature_names if c.startswith(prefix))
    covered = validate_feature_dict({hit_col: 1})["groups_covered"]
    assert covered["flat_plan"] is True
    assert covered["priorities"] is False
    assert covered["children"] is False
