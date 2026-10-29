"""
Загрузка модели классификации и SHAP-объяснителя (глобальные синглтоны).

Модель, SHAP-объяснитель и имена признаков строятся ОДИН раз при импорте
этого модуля (при старте контейнера) и кэшируются в глобальных переменных
— для скорости ответов.
"""

import os
import time

import joblib
import shap
from video_api.config import FEATURE_NAMES_PATH, MODEL_PATH


def _load_models():
    """Возвращает (model, explainer, feature_names).

    SHAP-объяснитель создаётся из модели на лету, потому что
    сериализованный xgb_explainer.joblib может быть несовместим
    с версией shap в образе (AttributeError: ... 'approximate').
    """
    model = joblib.load(MODEL_PATH)
    # Если модель — sklearn Pipeline (обёртка), извлекаем сам классификатор,
    # т.к. shap.TreeExplainer не поддерживает Pipeline напрямую.
    clf = model
    if hasattr(model, "named_steps") and len(model.named_steps) > 0:
        clf = list(model.named_steps.values())[-1]
    elif hasattr(model, "steps") and len(model.steps) > 0:
        clf = model.steps[-1][1]
    explainer = shap.TreeExplainer(clf)

    feature_names = None
    if os.path.exists(FEATURE_NAMES_PATH):
        with open(FEATURE_NAMES_PATH, encoding="utf-8") as f:
            feature_names = [line.strip() for line in f if line.strip()]
    else:
        # Берём имена признаков прямо из модели — надёжный fallback.
        try:
            if hasattr(model, "feature_names_in_"):
                feature_names = list(model.feature_names_in_)
            elif hasattr(model, "get_booster"):
                feature_names = model.get_booster().feature_names
        except Exception:
            feature_names = None
    return model, explainer, feature_names


model = None
explainer = None
FEATURE_NAMES = None
MODEL_LOAD_MS = 0
try:
    _t_load = time.monotonic()
    model, explainer, FEATURE_NAMES = _load_models()
    MODEL_LOAD_MS = int((time.monotonic() - _t_load) * 1000)
    print(
        f"Models loaded OK in {MODEL_LOAD_MS} ms. "
        f"Features: {len(FEATURE_NAMES) if FEATURE_NAMES else 'n/a'}"
    )
except Exception as exc:  # pragma: no cover
    print(f"FATAL: failed to load models at startup: {exc}")
    # Не роняем процесс сразу: /health расскажет о проблеме, а /generate
    # вернёт 500.

# Счётчик инференсов процесса: первый вызов после старта помечаем
# «холодным» (cold) для метрик p50/p95 отдельно по cold/warm.
_INFERENCE_NO = 0


def _next_inference_no() -> int:
    global _INFERENCE_NO
    _INFERENCE_NO += 1
    return _INFERENCE_NO
