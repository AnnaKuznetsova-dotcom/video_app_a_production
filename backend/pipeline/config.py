"""Этап 0 — Конфигурация конвейера.

Собраны все константы и чтение переменных окружения: доступ к S3,
пути к артефактам модели и карты соответствий (посёлок -> фиксированный
ролик, класс -> посёлок). Ни один другой модуль pipeline не читает env напрямую.
"""

import os

# -----------------------------------------------------------------------
# 1. НАСТРОЙКА ОКРУЖЕНИЯ: S3 / Yandex Object Storage
# -----------------------------------------------------------------------
BUCKET_NAME = os.getenv("BUCKET_NAME")
S3_ENDPOINT = os.getenv("YC_S3_ENDPOINT", "https://storage.yandexcloud.net")
# Папка с готовыми роликами в бакете (вариант A): video/Kaskad_Video/.
VIDEO_S3_ROOT = os.getenv("VIDEO_S3_ROOT", "video/Kaskad_Video")

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None

# S3-клиент создаём только при полном наборе креденшелов. Если их нет —
# работаем в локальном режиме (раздача роликов из backend/media), чтобы
# вариант A можно было проверять в Streamlit без внешнего хранилища.
_S3_READY = bool(boto3) and bool(
    BUCKET_NAME and os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")
)
if _S3_READY:
    _session = boto3.session.Session()
    s3_client = _session.client(
        service_name="s3",
        endpoint_url=S3_ENDPOINT,
        region_name=os.getenv("YC_S3_REGION", "ru-central1"),
    )
    print(f"A: S3 mode enabled (bucket={BUCKET_NAME}, root={VIDEO_S3_ROOT})")
else:
    s3_client = None
    print("A: S3 creds not set — LOCAL fixed-media mode (backend/media)")

# Родитель каталога pipeline (= backend, а в контейнере — /app).
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# -----------------------------------------------------------------------
# 2. ПУТИ К МОДЕЛИ И ДАННЫМ
# -----------------------------------------------------------------------
MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/global_best_model.joblib")
FEATURE_NAMES_PATH = os.getenv("FEATURE_NAMES_PATH", "/app/data/feature_names.txt")

# Папка с ГОТОВЫМИ фиксированными роликами посёлка (вариант A).
MEDIA_DIR = os.getenv("MEDIA_DIR", os.path.join(BACKEND_ROOT, "media"))

# -----------------------------------------------------------------------
# 3. БИЗНЕС-КАРТЫ: классификатор -> посёлок -> фиксированный ролик.
#    Для варианта A ролик НЕ зависит от ответов пользователя
#    (только от предсказанного посёлка) — это и есть контроль.
# -----------------------------------------------------------------------
CLASS_MAP = {
    0: "Kaskad_Park",
    1: "Akademia_Park",
    2: "Fedoskino_Park",
    3: "Park_Aprel",
}

FIXED_VIDEO_BY_SETTLEMENT = {
    "Kaskad_Park": "Каскад_Парк.mp4",
    "Akademia_Park": "Академия_Парк.mp4",
    "Fedoskino_Park": "Федоскино_Парк.mp4",
    "Park_Aprel": "Парк_Апрель.mp4",
}
