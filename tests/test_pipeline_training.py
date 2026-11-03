"""Юнит-тесты этапа model training (переобучение) — синтетический датасет.

Проверяем:
  - `model_update.dataset_validation.validate_dataset` — пороги отбраковки
    данных (нет target, пропуски >10%, дубли >5%, класс >80%);
  - `model_update.training.split_dataset` — пропорции 70/15/15;
  - `model_update.training.train_candidate` — честное обучение XGBoost на
    маленьком отделимом датасете → joblib-кандидат в реестре версий.
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

from pipeline import model_registry as reg  # noqa: E402
from pipeline.model_update import dataset_validation as dv  # noqa: E402
from pipeline.model_update import training  # noqa: E402

N_CLASSES = 4


def _clean_csv(tmp_path, rows_per_class=60, n_features=6) -> str:
    """Отделимый 4-классовый датасет: класс = номер строки mod 4.

    Все фичи повторяют класс + один числовой признак делает каждую строку
    уникальной (чтобы не упереться в порог дубликатов валидации)."""
    values = pd.Series([i % N_CLASSES for i in range(N_CLASSES * rows_per_class)])
    data = {f"f{k}": values.astype(float) for k in range(1, n_features)}
    data["row_id"] = [i / 1000.0 for i in range(N_CLASSES * rows_per_class)]
    data["target"] = values
    df = pd.DataFrame(data)
    path = tmp_path / "dataset.csv"
    df.to_csv(path, index=False)
    return str(path)


def _write_csv(tmp_path, df: pd.DataFrame, name="bad.csv") -> str:
    path = tmp_path / name
    df.to_csv(path, index=False)
    return str(path)


# ---------------------------------------------------------------------------
# validate_dataset — пороги отбраковки
# ---------------------------------------------------------------------------
def test_validate_clean_dataset_ok(tmp_path):
    report = dv.validate_dataset(_clean_csv(tmp_path))
    assert report["ok"] is True
    assert report["failures"] == []
    assert report["rows"] == N_CLASSES * 60


def test_validate_missing_target(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    report = dv.validate_dataset(_write_csv(tmp_path, df))
    assert report["ok"] is False
    assert any(f["code"] == "no_target" for f in report["failures"])


def test_validate_too_many_missing(tmp_path):
    df = pd.DataFrame({"a": [1] * 10 + [None] * 10, "target": [0, 1] * 10})
    report = dv.validate_dataset(_write_csv(tmp_path, df))
    assert report["ok"] is False
    assert any(f["code"] == "too_many_missing" for f in report["failures"])


def test_validate_too_many_duplicates(tmp_path):
    row = {"a": 1.0, "b": 2.0, "c": 3.0, "target": 0}
    df = pd.DataFrame([row] * 10 + [{"a": 9.0, "b": 9.0, "c": 9.0, "target": 3}])
    report = dv.validate_dataset(_write_csv(tmp_path, df))
    assert report["ok"] is False
    assert any(f["code"] == "too_many_duplicates" for f in report["failures"])


def test_validate_class_imbalance(tmp_path):
    n_majority = 90
    df = pd.DataFrame(
        {
            "a": list(range(n_majority)) + [100, 101],
            "target": [0] * n_majority + [3, 3],
        }
    )
    report = dv.validate_dataset(_write_csv(tmp_path, df))
    assert report["ok"] is False
    assert any(f["code"] == "class_imbalance" for f in report["failures"])


# ---------------------------------------------------------------------------
# split_dataset — пропорции 70 / 15 / 15
# ---------------------------------------------------------------------------
def test_split_dataset_proportions(tmp_path):
    df = pd.read_csv(_clean_csv(tmp_path))
    train_df, val_df, test_df = training.split_dataset(df)
    n = len(df)
    assert len(train_df) == int(0.70 * n)
    assert len(val_df) == int(0.15 * n)
    assert len(test_df) + len(val_df) + len(train_df) == n
    # стратификация: в каждой выборке представлены все 4 класса
    assert sorted(train_df["target"].unique()) == [0, 1, 2, 3]
    assert sorted(test_df["target"].unique()) == [0, 1, 2, 3]


def test_split_deterministic_with_seed(tmp_path):
    df = pd.read_csv(_clean_csv(tmp_path))
    a = training.split_dataset(df)
    b = training.split_dataset(df)
    assert a[0].index.equals(b[0].index)  # seed=42 → воспроизводимо


# ---------------------------------------------------------------------------
# train_candidate — конец-конец с настоящим XGBoost (маленький датасет)
# ---------------------------------------------------------------------------
def test_train_candidate_writes_joblib(tmp_path, monkeypatch):
    csv_path = _clean_csv(tmp_path, rows_per_class=50)
    model_dir = tmp_path / "model"
    monkeypatch.setattr(reg, "_MODEL_DIR", str(model_dir))

    result = training.train_candidate(csv_path)
    assert os.path.exists(result["candidate_path"])
    assert result["candidate_path"].startswith(str(model_dir))
    assert result["snapshot_version"].startswith("model_v")
    assert set(result["metrics"]) >= {"val_accuracy", "test_accuracy", "rows"}
    # синтетика отделима — обе выборки в идеале 1.0
    assert result["metrics"]["val_accuracy"] > 0.9
    assert result["metrics"]["test_accuracy"] > 0.9


def test_train_candidate_rejects_bad_dataset(tmp_path, monkeypatch):
    bad = pd.DataFrame({"a": [1, 2], "b": [3, 4]})  # нет target
    bad_path = _write_csv(tmp_path, bad)
    monkeypatch.setattr(reg, "_MODEL_DIR", str(tmp_path / "model"))
    with pytest.raises(ValueError, match="no_target"):
        training.train_candidate(bad_path)


def test_versions_dir_exists_in_registry():
    """Реестр версий по умолчанию смотрит в backend/model/versions."""
    assert reg.versions_dir().endswith(os.path.join("model", "versions"))
