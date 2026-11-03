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
    """Читает имена признаков модели из feature_names.txt (одна на строку).

    Порядок источников:
      1) явный аргумент `path`;
      2) FEATURE_NAMES_PATH из окружения (путь контейнера /app/data/...);
      3) локальный файл репозитория backend/data/feature_names.txt
         (нужен для отладки вне контейнера и для тестов).
    """
    from pipeline.config import BACKEND_ROOT, FEATURE_NAMES_PATH

    candidates = [path, FEATURE_NAMES_PATH, os.path.join(BACKEND_ROOT, "data", "feature_names.txt")]
    for cand in candidates:
        try:
            if cand and os.path.exists(cand):
                with open(cand, encoding="utf-8") as f:
                    names = [line.strip() for line in f if line.strip()]
                if names:
                    return names
        except OSError:
            continue
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
