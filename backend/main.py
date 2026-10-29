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
Всё остальное (модель, SHAP-группировка, ответ /predict и /generate,
фронт-агрегаты, метрики) — как в изначальной версии video-app.

Роль сервиса:
    1) Принимает от Streamlit полный ВЕКТОР ПРИЗНАКОВ покупателя (JSON dict).
    2) Загружает модель классификации (global_best_model.joblib) и
       строит SHAP-объяснитель на лету.
    3) Предсказывает класс посёлка (settlement).
    4) Считает SHAP-значения и группирует факторы (для графика на фронте).
    5) Возвращает публичную ссылку на фиксированный ролик посёлка
       (/media/<файл>) + метаданные.

Эндпоинты:
    GET  /health          — проверка живости контейнера и наличия моделей.
    POST /predict         — только предсказание класса + топ факторов SHAP.
    POST /generate/       — предсказание + ссылка на фиксированный ролик.
    GET  /metrics         — сводка технических метрик.

Этот файл — ТОНКАЯ ТОЧКА ВХОДА: создаёт FastAPI-приложение и
регистрирует маршруты из пакета video_api (см. video_api/routes.py).
Запуск: uvicorn main:app (из каталога backend, WORKDIR=/app в контейнере).
"""

import os
import sys

# Локальные запуски `python backend/main.py`: папка backend может не быть
# на sys.path — добавляем её, чтобы работали `import metrics` и `import video_api`.
# В контейнере WORKDIR=/app и файлы скопированы в корень, поэтому это
# дополнение безопасно (путь уже на sys.path).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from fastapi import FastAPI
from video_api.routes import register_routes

# -----------------------------------------------------------------------
# FASTAPI APP (тонкая точка входа)
# -----------------------------------------------------------------------
app = FastAPI(title="Video API (A · фиксированный ролик)", version="1.0.0")

# Все эндпоинты (/health, /predict, /metrics, /admin/reset_metrics,
# /generate/) и статический монтиж /media — в video_api/routes.py.
register_routes(app)
