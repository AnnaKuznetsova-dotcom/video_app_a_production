"""Шаг BPMN «Проверка качества кандидата» против baseline.

Пороги Model_retrain_BPMN.md (§3, этап 7): кандидат допускается к
согласованию с бизнесом, только если:

    Accuracy  — не ниже baseline более чем на 3 п.п.
    Recall macro — не ниже baseline более чем на 5 п.п.

Baseline хранится в model/baseline_metrics.json (пишется при выпуске
предыдущей production-версии см. promotion.py).
"""

import json
import os

from pipeline.model_update import dataset_validation
from sklearn.metrics import accuracy_score, recall_score

BASELINE_FILENAME = "baseline_metrics.json"
DELTA_ACCURACY = 0.03
DELTA_RECALL = 0.05


def baseline_path() -> str:
    import os as _os

    from pipeline.model_registry import versions_dir

    return _os.path.join(_os.path.dirname(versions_dir()), BASELINE_FILENAME)


def evaluate_candidate(model, test_df, target_col=dataset_validation.TARGET_COLUMN) -> dict:
    """Метрики кандидата на отложенном test-сете: accuracy + macro recall."""
    feature_cols = [c for c in test_df.columns if c != target_col]
    y_true = test_df[target_col]
    y_pred = model.predict(test_df[feature_cols])
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "recall_macro": round(float(recall_score(y_true, y_pred, average="macro")), 4),
    }


def passes_thresholds(candidate_metrics: dict) -> dict:
    """Сравнение метрик кандидата с baseline. Возвращает::

    {"ok": bool, "checks": [{name, value, baseline, delta_allowed, ok}, ...]}
    """
    with open(baseline_path(), encoding="utf-8") as f:
        baseline = json.load(f)

    checks = []
    acc, acc_b = candidate_metrics["accuracy"], baseline.get("accuracy")
    rec, rec_b = candidate_metrics["recall_macro"], baseline.get("recall_macro")
    checks.append(
        {
            "name": "accuracy",
            "value": acc,
            "baseline": acc_b,
            "delta_allowed": DELTA_ACCURACY,
            "ok": acc >= acc_b - DELTA_ACCURACY,
        }
    )
    checks.append(
        {
            "name": "recall_macro",
            "value": rec,
            "baseline": rec_b,
            "delta_allowed": DELTA_RECALL,
            "ok": rec >= rec_b - DELTA_RECALL,
        }
    )
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def baseline_exists() -> bool:
    return os.path.exists(baseline_path())
