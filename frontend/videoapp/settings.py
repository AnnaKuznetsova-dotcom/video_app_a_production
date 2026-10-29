"""Конфигурация окружения: URL бэкенда, пути к данным, каталог проектов.

Нижний слой пакета videoapp: зависит только от Streamlit (для st.secrets).
"""

import os

import streamlit as st

# frontend/ — на уровень выше пакета videoapp (пути к data/ должны вести
# в frontend/data, как это было в исходном app.py).
_FRONTEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# КОНФИГУРАЦИЯ
# ---------------------------------------------------------------------------
def _resolve_backend_url() -> str:
    try:
        s = st.secrets.get("BACKEND_URL", "")
    except Exception:
        s = ""
    if not s:
        s = os.getenv("BACKEND_URL", "http://localhost:8080")
    return s.rstrip("/")


BACKEND_URL = _resolve_backend_url()

USE_CUSTOM_PLAYER = True

FEATURES_PATH = os.path.join(_FRONTEND_DIR, "data", "feature_names.txt")
MODEL_PATH = os.path.join(_FRONTEND_DIR, "data", "global_best_model.joblib")

# Как часто (сек) фронтенд обращается к /health бэкенда. Кэш в session_state
# избавляет от блокирующего сетевого запроса при каждом клике в опроснике
# (именно он вызывал «белый экран»/подвисание при вводе).
HEALTH_CHECK_TTL = 30

# Таймаут отдельного запроса /health. 8 c слишком мало при редком холодном
# старте (прогрев моделей ~14 c) — фронт рвал соединение и получал 499.
# Прогретый инстанс (--min-instances) отвечает за ~0.1-1 c, а 20 c — запас
# на случай, если контейнер всё же только что проснулся.
HEALTH_CHECK_TIMEOUT = 20


SETTLEMENT_NAMES = {
    "Kaskad_Park": "Каскад Парк",
    "Akademia_Park": "Академия Парк",
    "Fedoskino_Park": "Федоскино Парк",
    "Park_Aprel": "Парк Апрель",
}

SETTLEMENT_IMG = {
    "Kaskad_Park": "kaskad_park_1.jpg",
    "Akademia_Park": "akademiya_park.jpg",
    "Fedoskino_Park": "fedoskino_park_2.jpg",
    "Park_Aprel": "park_april_1.jpg",
}

# Проекты компании (video_app_a данные): только 4 разрешённых посёлка.
PROJECTS_SHOWCASE = [
    {
        "name": "Каскад Парк",
        "key": "Kaskad_Park",
        "meta": "Готовый жилой комплекс в Подольске",
        "img": "kaskad_park_1.jpg",
        "url": "https://kaskad-park.ru/",
        "price": "от 15 млн ₽",
        "distance": "19 км от МКАД",
        "highway": "Симферопольское шоссе",
        "features": [
            "рыболовный клуб",
            "школа",
            "детский сад",
            "спортплощадки",
            "прогулочный бульвар",
            "магазины и кафе",
            "закрытая территория",
        ],
    },
    {
        "name": "Академия Парк",
        "key": "Akademia_Park",
        "meta": "Коттеджный посёлок в Новой Москве",
        "img": "akademiya_park.jpg",
        "url": "https://akademiya-park.ru/",
        "price": "от 25 млн ₽",
        "distance": "22 км от МКАД",
        "highway": "Киевское шоссе",
        "features": [
            "5 Га леса",
            "частный детский сад",
            "международная школа Внуково",
            "кофейня",
            "спортплощадки",
            "площадки для падела",
            "велодорожки",
            "закрытая охраняемая территория",
        ],
    },
    {
        "name": "Федоскино Парк",
        "key": "Fedoskino_Park",
        "meta": "Загородные резиденции у большой воды",
        "img": "fedoskino_park_2.jpg",
        "url": "https://fedoskino-park.ru/",
        "price": "от 15 млн ₽ (дуплексы)",
        "distance": "15 км от МКАД",
        "highway": "Дмитровское шоссе",
        "features": ["большая вода", "лес", "частный причал", "закрытая территория"],
    },
    {
        "name": "Парк Апрель",
        "key": "Park_Aprel",
        "meta": "Новый формат загородной жизни",
        "img": "park_april_1.jpg",
        "url": "https://p-aprel.ru/",
        "price": "уточняйте у менеджера",
        "distance": "25 км от МКАД",
        "highway": "Симферопольское шоссе",
        "features": ["природное окружение", "детские площадки"],
    },
]


def project_by_settlement(settlement_key: str) -> dict | None:
    """Возвращает карточку проекта по ключу посёлка (Kaskad_Park и т.д.)."""
    for p in PROJECTS_SHOWCASE:
        if p.get("key") == settlement_key:
            return p
    return None
