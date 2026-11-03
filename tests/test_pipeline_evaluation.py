"""Юнит-тесты подсчёта метрик качества кандидата (model_update.evaluation).

Проверяем:
  - `evaluate_candidate` — accuracy/recall_macro считаются верно на dummy-модели;
  - `passes_thresholds` — сравнение с baseline и допуск ±Δ; отказ при
    деградации; поведение при отсутствии baseline-файла.
"""

import json
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
from pipeline.model_update import evaluation as ev  # noqa: E402


class AlwaysOne:
    """Модель-болванка: всегда предсказывает класс 1."""

    def predict(self, X):
        return [1] * len(X)


@pytest.fixture
def eval_env(tmp_path, monkeypatch):
    """Указывает реестр версий и baseline на временный каталог model/."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    monkeypatch.setattr(reg, "_MODEL_DIR", str(model_dir))
    return model_dir


def test_evaluate_candidate_counts_correctly(eval_env):
    y_true = [1, 1, 1, 0]
    test_df = pd.DataFrame({"f0": [1, 1, 1, 0], "target": y_true})
    metrics = ev.evaluate_candidate(AlwaysOne(), test_df)
    assert metrics["accuracy"] == 0.75  # 3 верных из 4
    assert metrics["recall_macro"] == pytest.approx(0.5)  # класс 0: recall 0


def test_passes_thresholds_ok(eval_env):
    baseline = {"accuracy": 0.80, "recall_macro": 0.78}
    with open(ev.baseline_path(), "w", encoding="utf-8") as f:
        json.dump(baseline, f)
    result = ev.passes_thresholds({"accuracy": 0.80, "recall_macro": 0.75})
    assert result["ok"] is True
    assert all(c["ok"] for c in result["checks"])


def test_passes_thresholds_marginal_still_ok(eval_env):
    with open(ev.baseline_path(), "w", encoding="utf-8") as f:
        json.dump({"accuracy": 0.80, "recall_macro": 0.78}, f)
    # ровно на границе допустимой деградации (−3 п.п. accuracy)
    result = ev.passes_thresholds({"accuracy": 0.77, "recall_macro": 0.73})
    assert result["ok"] is True


def test_passes_thresholds_rejects_degraded(eval_env):
    with open(ev.baseline_path(), "w", encoding="utf-8") as f:
        json.dump({"accuracy": 0.80, "recall_macro": 0.78}, f)
    result = ev.passes_thresholds({"accuracy": 0.70, "recall_macro": 0.78})
    assert result["ok"] is False
    failed = [c["name"] for c in result["checks"] if not c["ok"]]
    assert failed == ["accuracy"]


def test_baseline_path_is_derived_from_versions_dir(eval_env):
    assert ev.baseline_path() == str(eval_env / "baseline_metrics.json")


def test_baseline_exists_flag(eval_env):
    assert ev.baseline_exists() is False
    with open(ev.baseline_path(), "w", encoding="utf-8") as f:
        json.dump({"accuracy": 0.9, "recall_macro": 0.9}, f)
    assert ev.baseline_exists() is True
