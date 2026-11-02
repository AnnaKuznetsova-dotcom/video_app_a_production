"""Этап 3 — Model inference: загрузка модели и предсказание посёлка.

Модель загружается ОДИН раз при импорте модуля (старт контейнера) и кэшируется
в глобальных переменных — для скорости ответов. Первый инференс после старта
помечается как «холодный» (is_cold) для метрик p50/p95.
"""

import time

import joblib
from pipeline.config import CLASS_MAP, FEATURE_NAMES_PATH, MODEL_PATH


def _load_model() -> object:
    """Загружает joblib-модель и (fallback) имена признаков из самого объекта."""
    model = joblib.load(MODEL_PATH)
    if not FEATURES_AVAILABLE():
        from pipeline import data_preprocessing

        try:
            names = None
            if hasattr(model, "feature_names_in_"):
                names = list(model.feature_names_in_)
            elif hasattr(model, "get_booster"):
                names = model.get_booster().feature_names
            if names:
                data_preprocessing.FEATURE_NAMES = list(names)
        except Exception:
            pass
    return model


def FEATURES_AVAILABLE() -> bool:
    """True, если список колонок модели уже известен preprocessing-этапу."""
    from pipeline import data_preprocessing

    return bool(data_preprocessing.FEATURE_NAMES)


def _read_feature_names():
    """Читает feature_names.txt с диска (если файл существует)."""
    try:
        with open(FEATURE_NAMES_PATH, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return None


model = None
MODEL_LOAD_MS = 0
try:
    _t_load = time.monotonic()
    _names = _read_feature_names()
    if _names:
        from pipeline import data_preprocessing

        data_preprocessing.FEATURE_NAMES = _names
    model = _load_model()
    MODEL_LOAD_MS = int((time.monotonic() - _t_load) * 1000)
    print(f"Model loaded OK in {MODEL_LOAD_MS} ms")
except Exception as exc:  # pragma: no cover
    print(f"FATAL: failed to load model at startup: {exc}")
    # Не роняем процесс сразу: /health расскажет о проблеме, а /generate
    # вернёт 500.

# Счётчик инференсов процесса: первый вызов после старта помечаем
# «холодным» (cold) для метрик p50/p95 отдельно по cold/warm.
_INFERENCE_NO = 0


def next_inference_no() -> int:
    """Инкрементирует и возвращает номер инференса в жизни процесса."""
    global _INFERENCE_NO
    _INFERENCE_NO += 1
    return _INFERENCE_NO


def predict_settlement(feature_frame) -> tuple[int, str]:
    """Предсказание: DataFrame признаков → (класс, посёлок).

    Единственная точка, где модель касается данных: routes/serving и
    model_update/evaluation обязаны ходить только через неё.
    """
    klass = int(model.predict(feature_frame)[0])
    settlement = CLASS_MAP.get(klass, "Kaskad_Park")
    return klass, settlement


def is_model_ready() -> bool:
    """Модель загрузилась и готова к инференсу."""
    return model is not None


def model_load_ms() -> int:
    """Время загрузки joblib-артефакта при старте (для метрики cold-start)."""
    return MODEL_LOAD_MS


__all__ = ["model", "MODEL_LOAD_MS", "predict_settlement", "is_model_ready", "next_inference_no"]
