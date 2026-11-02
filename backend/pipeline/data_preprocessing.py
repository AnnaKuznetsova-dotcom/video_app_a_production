"""Этап 1 — Data preprocessing.

Преобразует вектор признаков, присланный Streamlit (JSON dict), в DataFrame
ровно той структуры, которую ждёт модель: полный набор колонок
(`feature_names.txt`), числовые значения, нули вместо пропусков.

Результат этого этапа передаётся в model_inference.predict_settlement().
"""

import os
from typing import Any

import pandas as pd

FEATURE_NAMES: list[str] = []


def load_feature_names(path: str | None = None) -> list[str]:
    """Читает имена признаков модели из feature_names.txt (одна на строку)."""
    from pipeline.config import FEATURE_NAMES_PATH

    path = path or FEATURE_NAMES_PATH
    try:
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                names = [line.strip() for line in f if line.strip()]
            if names:
                return names
    except OSError:
        pass
    return list(FEATURE_NAMES)


FEATURE_NAMES = load_feature_names()


def load_feature_frame(features: dict[str, Any]) -> pd.DataFrame:
    """Словарь признаков от Streamlit → DataFrame структуры модели.

    Гарантии:
      - колонки строго совпадают со списком признаков модели (порядок важен);
      - все значения числовые, пропуски/битые значения заменены нулём.
    """
    frame = pd.DataFrame([features])
    if FEATURE_NAMES:
        frame = frame.reindex(columns=FEATURE_NAMES, fill_value=0)
    frame = frame.fillna(0)
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)
    return frame


# Историческое имя функции (использовалось в исходном репозитории video_app_a).
_try_load_feature_frame = load_feature_frame
