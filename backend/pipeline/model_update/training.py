"""Шаг BPMN «Обучение кандидата»: XGBoost на валидированном датасете.

Правила Model_retrain_BPMN.md:
    split train 70% / val 15% / test 15%, стратификация по классам, seed=42;
    результат — joblib-кандидат + evaluation_mapping с метриками на val/test.

Запуск вручную::

    cd backend
    python -m pipeline.model_update.training --dataset data/dataset_v20260101.csv

Скрипт НЕ ставит модель в production: кандидат кладётся в
pipeline.model_registry.versions_dir() и ждёт шага evaluation → promotion.
"""

import argparse
import os
import time

import joblib
import pandas as pd
from pipeline.model_update import dataset_validation
from sklearn.model_selection import train_test_split

SEED = 42
TARGET_COLUMN = dataset_validation.TARGET_COLUMN


def split_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Стратифицированное разбиение 70/15/15 с фиксированным seed."""
    y = df[TARGET_COLUMN]
    train_df, tmp_df = train_test_split(df, test_size=0.30, stratify=y, random_state=SEED)
    val_df, test_df = train_test_split(
        tmp_df, test_size=0.50, stratify=tmp_df[TARGET_COLUMN], random_state=SEED
    )
    return train_df, val_df, test_df


def train_candidate(csv_path: str, out_dir: str | None = None) -> dict:
    """Обучает кандидата и сохраняет артефакт. Возвращает::

    {"candidate_path": str, "snapshot_version": str,
     "metrics": {"val_accuracy": ..., "test_accuracy": ...},
     "dataset": {… report из dataset_validation, "split": {...}}}
    """
    report = dataset_validation.validate_dataset(csv_path)
    if not report["ok"]:
        raise ValueError(f"Dataset failed validation: {report['failures']}")

    df = pd.read_csv(csv_path)
    train_df, val_df, test_df = split_dataset(df)
    feature_cols = [c for c in df.columns if c != TARGET_COLUMN]

    from xgboost import XGBClassifier

    clf = XGBClassifier(random_state=SEED, eval_metric="mlogloss")
    clf.fit(train_df[feature_cols], train_df[TARGET_COLUMN])

    metrics = {
        "val_accuracy": round(float(clf.score(val_df[feature_cols], val_df[TARGET_COLUMN])), 4),
        "test_accuracy": round(float(clf.score(test_df[feature_cols], test_df[TARGET_COLUMN])), 4),
        "rows": {"train": len(train_df), "val": len(val_df), "test": len(test_df)},
    }

    version = f"model_v{time.strftime('%Y%m%d')}_{os.getpid()}"
    from pipeline.model_registry import versions_dir

    out_dir = out_dir or versions_dir()
    os.makedirs(out_dir, exist_ok=True)
    candidate_path = os.path.join(out_dir, f"{version}.joblib")
    joblib.dump(clf, candidate_path)

    return {
        "candidate_path": candidate_path,
        "snapshot_version": version,
        "metrics": metrics,
        "dataset": {"source": csv_path, "validation": report},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучение кандидата модели посёлка")
    parser.add_argument("--dataset", required=True, help="CSV c колонками признаков + target")
    args = parser.parse_args()
    result = train_candidate(args.dataset)
    print(f"Candidate saved: {result['candidate_path']}")
    print(f"Metrics: {result['metrics']}")
    print("Next step: pipeline.model_update.evaluation — сравнить с baseline.")


if __name__ == "__main__":
    main()
