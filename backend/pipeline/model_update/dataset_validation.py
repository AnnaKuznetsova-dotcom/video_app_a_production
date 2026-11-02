"""Шаг BPMN «Проверка пригодности данных» перед переобучением (см. Model_retrain_BPMN.md, §5).

Пороги отказа (совпадают с Model_retrain_BPMN.md):
    пропусков в обязательных полях   > 10%
    дубликатов                       > 5%
    максимальная доля одного класса  > 80%
    признак target                     отсутствует
Каждая причина отказа возвращается явно — её фиксируют в журнале аудита.
"""

import pandas as pd

MAX_MISSING_SHARE = 0.10
MAX_DUPLICATE_SHARE = 0.05
MAX_CLASS_SHARE = 0.80
TARGET_COLUMN = "target"


def validate_dataset(csv_path: str) -> dict:
    """Проверяет датасет по порогам BPMN. Возвращает::

    {
      "ok": bool,
      "rows": int,
      "failures": [ {code, detail}, ... ],
      "class_share_max": float, "missing_share_max": float,
      "duplicate_share": float,
    }
    """
    failures: list[dict] = []
    df = pd.read_csv(csv_path)
    rows = len(df)

    # 1) Обязательная целевая колонка.
    if TARGET_COLUMN not in df.columns:
        failures.append({"code": "no_target", "detail": f"нет колонки {TARGET_COLUMN}"})

    # 2) Пропуски в каждой колонке.
    missing = df.isna().mean()
    missing_share = float(missing.max()) if len(df) else 0.0
    if missing_share > MAX_MISSING_SHARE:
        failures.append(
            {
                "code": "too_many_missing",
                "detail": f"{missing.idxmax()} пропущено {missing_share:.0%} (> {MAX_MISSING_SHARE:.0%})",
            }
        )

    # 3) Дубликаты строк.
    duplicate_share = float(df.duplicated().mean()) if rows else 0.0
    if duplicate_share > MAX_DUPLICATE_SHARE:
        failures.append(
            {
                "code": "too_many_duplicates",
                "detail": f"{duplicate_share:.0%} (> {MAX_DUPLICATE_SHARE:.0%})",
            }
        )

    # 4) Небаланс классов.
    class_share_max = (
        float(df[TARGET_COLUMN].value_counts(normalize=True).max())
        if rows and TARGET_COLUMN in df
        else 0.0
    )
    if class_share_max > MAX_CLASS_SHARE:
        failures.append(
            {
                "code": "class_imbalance",
                "detail": f"один класс занимает {class_share_max:.0%} (> {MAX_CLASS_SHARE:.0%})",
            }
        )

    return {
        "ok": not failures,
        "rows": rows,
        "failures": failures,
        "class_share_max": class_share_max,
        "missing_share_max": missing_share,
        "duplicate_share": duplicate_share,
    }
