"""Интеграционный тест контура переобучения (Model_retrain_BPMN.md, шаги 2–9).

Полный прогон на синтетическом датасете:
    валидация данных → обучение кандидата (XGBoost) → подсчёт метрик →
    baseline-сравнение → promotion (регистрация версии + производство файл).

Проверяем, что этапы передают друг другу правильно:
    candidate_model_vN.joblib  →  baseline_metrics.json  →  versions/ +
    active_model.txt  +  global_best_model.joblib (production-артефакт).
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
from pipeline.model_update import dataset_validation as dv  # noqa: E402
from pipeline.model_update import evaluation as ev  # noqa: E402
from pipeline.model_update import promotion, training  # noqa: E402


def _clean_csv(tmp_path, rows_per_class=50, n_features=6) -> str:
    rng = pd.Series([i % 4 for i in range(4 * rows_per_class)])
    data = {f"f{k}": rng.astype(float) for k in range(1, n_features)}
    data["row_id"] = [i / 1000.0 for i in range(4 * rows_per_class)]
    data["target"] = rng
    path = tmp_path / "dataset.csv"
    pd.DataFrame(data).to_csv(path, index=False)
    return str(path)


@pytest.fixture
def retrain_env(tmp_path, monkeypatch):
    """Временный «model/»-каталог для promotion и реестра."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    monkeypatch.setattr(reg, "_MODEL_DIR", str(model_dir))
    monkeypatch.setattr(promotion, "_MODEL_DIR", str(model_dir))
    return model_dir


def test_full_retrain_loop(tmp_path, retrain_env):
    # 1. Валидация данных
    csv_path = _clean_csv(tmp_path)
    report = dv.validate_dataset(csv_path)
    assert report["ok"] is True

    # 2-3. Обучение кандидата (настоящий XGBoost, маленький отделимый датасет)
    result = training.train_candidate(csv_path)
    candidate_path = result["candidate_path"]
    assert os.path.exists(candidate_path)
    assert result["metrics"]["test_accuracy"] > 0.9

    # 4. Baseline «текущей» версии — ставим чуть ниже кандидата, чтобы прошёл порог
    baseline = {"accuracy": 0.70, "recall_macro": 0.70}
    with open(ev.baseline_path(), "w", encoding="utf-8") as f:
        json.dump(baseline, f)

    # Метрики в формате счётчика порогов (accuracy + recall_macro)
    candidate_metrics = {
        "accuracy": result["metrics"]["test_accuracy"],
        "recall_macro": result["metrics"]["test_accuracy"],
    }

    # Проверка качества (шаг evaluation на этих же метриках кандидата)
    gate = ev.passes_thresholds(candidate_metrics)
    assert gate["ok"] is True

    # 5. Registration / promotion: версия записывается в реестр + production-файл
    promoted = promotion.promote_candidate(
        candidate_path, metrics=candidate_metrics, approved_by="manager@example.com"
    )
    filename = os.path.basename(candidate_path)
    assert os.path.exists(promoted["artifact_path"])
    assert os.path.exists(os.path.join(str(retrain_env), filename))
    assert os.path.exists(promoted["production_path"])
    assert reg.active_version() == filename
    with open(ev.baseline_path(), encoding="utf-8") as f:
        stored_baseline = json.load(f)
    assert stored_baseline["approved_by"] == "manager@example.com"
    assert stored_baseline["accuracy"] == pytest.approx(result["metrics"]["test_accuracy"])
    assert filename in reg.list_versions()


def test_promotion_requires_existing_candidate(retrain_env):
    with pytest.raises(FileNotFoundError):
        promotion.promote_candidate("model_v_missing.joblib", metrics={})
