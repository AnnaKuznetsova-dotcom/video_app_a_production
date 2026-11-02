"""ML-конвейер Video API (вариант A · контроль) — код разбит по этапам::

    pipeline/
    ├── config.py               — этап 0: конфигурация окружения (env, S3, пути)
    ├── data_preprocessing.py   — этап 1: восстановление вектора признаков → DataFrame
    ├── feature_generation.py   — этап 2: пространство признаков модели и его валидация
    ├── model_inference.py      — этап 3: загрузка модели и предсказание посёлка
    ├── model_registry.py       — этап 4: версии артефактов модели (active/архив)
    ├── model_update/           — этап 5: скелет контура переобучения (см. Model_retrain_BPMN.md)
    ├── metrics_tracker.py      — этап 6: сбор технических метрик (CSV + S3)
    └── serving/routes.py       — этап 7: HTTP-эндпоинты FastAPI

Философия: один файл = один этап конвейера; данные текут строго сверху вниз
(конфиг → preprocessing → inference → response), метрики пишутся сбоку.
"""

import os
import sys

# Локальные запуски `python backend/main.py`: папка backend может не быть
# на sys.path — добавляем её, чтобы работал `import pipeline` из любого cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
