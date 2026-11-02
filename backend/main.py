"""
Yandex Serverless Container — Video API (Вариант A · контроль).

От исходного конвейера отличается ТОЛЬКО способом генерации видеоролика:
вместо скачивания фрагментов из S3 и склейки (moviepy/ffmpeg) отдаётся
ГОТОВЫЙ фиксированный ролик посёлка — один и тот же для всех пользователей,
предсказавших этот посёлок (надписи на ролике уже вшиты в файл).
Хранилище готовых роликов: в bucket файлы лежат по пути `video/Kaskad_Video/`,
внутри — готовые ролики по посёлкам (`video/Kaskad_Video/<ИмяФайла.mp4>`);
в production /generate/ возвращает прямой публичный URL на этот объект,
при отладке без S3-креденшелов роль исполняет локальная раздача
backend/media (/media/...).

Роль сервиса (конвейер по этапам — см. backend/pipeline/):
    1) config                  — env/S3/карты посёлков;
    2) data_preprocessing      — вектор признаков от Streamlit → DataFrame модели;
    3) feature_generation      — контракт пространства признаков анкеты;
    4) model_inference         — загрузка joblib-модели, предсказание посёлка;
    5) model_registry/model_update — версии модели и контур обновления (скелет);
    6) metrics_tracker         — запись технических метрик инференса (CSV + S3);
    7) serving/routes          — эндпоинты ниже.

Эндпоинты:
    GET  /health          — проверка живости контейнера и наличия модели.
    POST /predict         — предсказание класса посёлка.
    POST /generate/       — предсказание + ссылка на фиксированный ролик.
    GET  /metrics         — сводка технических метрик.

Этот файл — ТОНКАЯ ТОЧКА ВХОДА: создаёт FastAPI-приложение и
регистрирует маршруты из пакета pipeline.serving.
Запуск: uvicorn main:app (из каталога backend, WORKDIR=/app в контейнере).
"""

import os
import sys

# Локальные запуски `python backend/main.py`: папка backend может не быть
# на sys.path — добавляем её, чтобы работал `import pipeline`.
# В контейнере WORKDIR=/app и файлы скопированы в корень, поэтому это
# дополнение безопасно (путь уже на sys.path).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from fastapi import FastAPI  # noqa: E402
from pipeline.serving.routes import register_routes  # noqa: E402

# -----------------------------------------------------------------------
# FASTAPI APP (тонкая точка входа)
# -----------------------------------------------------------------------
app = FastAPI(title="Video API (A · фиксированный ролик)", version="2.1.0")

# Все эндпоинты (/health, /predict, /metrics, /admin/reset_metrics,
# /generate/) и статический монтиж /media — в pipeline/serving/routes.py.
register_routes(app)
