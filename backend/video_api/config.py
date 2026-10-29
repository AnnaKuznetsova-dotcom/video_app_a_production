"""
Конфигурация окружения Video API (вариант A · контроль).

Собраны все константы и чтение переменных окружения: доступ к S3,
пути к моделям внутри контейнера, карты соответствий
(посёлок -> ролик, фактор -> подкатегория), группы SHAP-факторов.
"""

import os

# -----------------------------------------------------------------------
# 1. НАСТРОЙКА ОКРУЖЕНИЯ
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

# Пути к моделям ВНУТРИ контейнера (см. Dockerfile -> COPY model /app/model)
MODEL_PATH = os.getenv("MODEL_PATH", "/app/model/global_best_model.joblib")
EXPLAINER_PATH = os.getenv("EXPLAINER_PATH", "/app/model/xgb_explainer.joblib")
FEATURE_NAMES_PATH = os.getenv("FEATURE_NAMES_PATH", "/app/data/feature_names.txt")

# Папка с ГОТОВЫМИ фиксированными роликами посёлка (вариант A).
# Родитель каталога video_api (= backend, а в контейнере — /app).
MEDIA_DIR = os.getenv(
    "MEDIA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media"),
)

# Число факторов, которые берём после "общего вида"
MAX_SHAP_FACTORS = int(os.getenv("MAX_SHAP_FACTORS", "4"))
# Приоритет снизу-вверх: самый важный SHAP-фактор идёт ПОСЛЕ остальных?
INVERT_SHAP_ORDER = os.getenv("INVERT_SHAP_ORDER", "false").lower() == "true"

# Классификатор -> фиксированный ролик. Для варианта A ролик НЕ зависит от
# ответов пользователя (только от предсказанного посёлка) — это и есть контроль.
FIXED_VIDEO_BY_SETTLEMENT = {
    "Kaskad_Park": "Каскад_Парк.mp4",
    "Akademia_Park": "Академия_Парк.mp4",
    "Fedoskino_Park": "Федоскино_Парк.mp4",
    "Park_Aprel": "Парк_Апрель.mp4",
}

# Стандартная длительность фрагмента по категории (сек) — как на фронте:
# [общий вид (5с)] + выбранные факторы. Нужен для отчёта «фактор -> длительность».
FACTOR_DURATION_S = {
    "few_cat__есть_ли_дети": 4,
    "bin_num__отделка": 4,
    "bin_num__квартира_планировка": 5,
    "bin_num__приоритеты": 5,
}
OVERALL_DUR_S = 5

# -----------------------------------------------------------------------
# 2. МЭППИНГ SHAP-ФАКТОР -> ПУТЬ НА S3
#    (сохранён для единообразия логики выбора «видео-способных» факторов и
#     совместимости ответа с исходной версией; в варианте A скачивание
#     фрагментов не используется).
# -----------------------------------------------------------------------
VIDEO_PATH_MAP = {
    # категория (папка) -> вложенная подкатегория
    "bin_num__квартира_планировка_1_комн": ("flat_plan", "1_room"),
    "bin_num__квартира_планировка_2_комн": ("flat_plan", "2_rooms"),
    "bin_num__квартира_планировка_3_комн": ("flat_plan", "3_rooms"),
    "bin_num__квартира_планировка_4_комн": ("flat_plan", "4_rooms"),
    "bin_num__квартира_планировка_более_4_комн": ("flat_plan", "4_more_rooms"),
    "bin_num__квартира_планировка_студия": ("flat_plan", "studio"),
    "bin_num__квартира_планировка_missing": ("flat_plan", "other"),
    "bin_num__приоритеты_безопасность": ("priorities", "safety"),
    "bin_num__приоритеты_инфраструктура": ("priorities", "infrastructure"),
    "bin_num__приоритеты_контингент": ("priorities", "contingent"),
    "bin_num__приоритеты_природа_экология": ("priorities", "nature_ecology"),
    "bin_num__приоритеты_транспортная_доступность": ("priorities", "transport_accessibility"),
    "bin_num__приоритеты_missing": ("priorities", "other"),
    "bin_num__отделка_white_box": ("finishing", "white_box"),
    "bin_num__отделка_под_ключ": ("finishing", "turnkey"),
    "bin_num__отделка_под_отделку": ("finishing", "for_finishing"),
    "bin_num__отделка_missing": ("finishing", "other"),
    "few_cat__есть_ли_дети_Есть": ("children_exist", "Yes"),
    "few_cat__есть_ли_дети_Нет": ("children_exist", "No"),
    # Факторы, для которых ролика нет -> не попадают в ролик, но остаются
    # в упорядоченном SHAP-списке (Streamlit может показать их как текст).
    "ORD__РАНГ_ПЛОЩАДИ": None,
}

# -----------------------------------------------------------------------
# ГРУППЫ ФАКТОРОВ (для согласованного ролика и графика).
# Ролик берётся под выбранный клиентом вариант ВНУТРИ группы, а не под
# максимум SHAP по группе.
#  - prefix:       по этому префиксу группируются SHAP отдельных признаков.
#  - alt_prefix:   дополнительный префикс той же смысловой группы (если есть).
#  - clip_prefix:  префикс, по которому определяем ВЫБРАННЫЙ вариант для ролика
#                  (он же используется в VIDEO_PATH_MAP).
# -----------------------------------------------------------------------
GROUPS = [
    {
        "key": "flat_plan",
        "label": "Планировка",
        "prefix": "bin_num__квартира_планировка",
        "alt_prefix": "few_cat__количество_комнат",
        "clip_prefix": "bin_num__квартира_планировка",
    },
    {
        "key": "priorities",
        "label": "Приоритеты",
        "prefix": "bin_num__приоритеты",
        "alt_prefix": None,
        "clip_prefix": "bin_num__приоритеты",
    },
    {
        "key": "finishing",
        "label": "Отделка",
        "prefix": "bin_num__отделка",
        "alt_prefix": None,
        "clip_prefix": "bin_num__отделка",
    },
    {
        "key": "children",
        "label": "Дети",
        "prefix": "few_cat__есть_ли_дети",
        "alt_prefix": None,
        "clip_prefix": "few_cat__есть_ли_дети",
    },
]

# Читаемые подписи значений для графика (часть имени признака после группы).
GROUP_VALUE_LABELS = {
    "1_комн": "1 комната",
    "2_комн": "2 комнаты",
    "3_комн": "3 комнаты",
    "4_комн": "4 комнаты",
    "более_4_комн": "более 4 комнат",
    "студия": "студия",
    "missing": "особые пожелания",
    "безопасность": "Безопасность",
    "инфраструктура": "Инфраструктура",
    "контингент": "Контингент",
    "природа_экология": "Природа и экология",
    "транспортная_доступность": "Транспортная доступность",
    "white_box": "white box",
    "под_ключ": "под ключ",
    "под_отделку": "под отделку",
    "Есть": "Есть",
    "Нет": "Нет",
}

CLASS_MAP = {
    0: "Kaskad_Park",
    1: "Akademia_Park",
    2: "Fedoskino_Park",
    3: "Park_Aprel",
}
