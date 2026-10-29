"""
Frontend — персональный «AI-куратор» видео для покупателей элитной недвижимости
(таунхаусы в Подмосковье). Дизайн — Open Design (KASKAD green/white/gold).

Поток (алгоритм не меняется):
    1) Покупатель отвечает на короткую анкету (Open Design-дизайн + бегунок справа).
    2) Streamlit собирает полный вектор признаков (как в блокноте).
    3) Streamlit отправляет вектор в Backend (Yandex Serverless Container).
    4) Backend предсказывает класс, считает SHAP, склеивает ролик из кусков
       на Yandex Object Storage и возвращает публичную ссылку.
    5) Streamlit показывает готовый ролик покупателя (Open Design-оформление).

Это ТОНКАЯ ТОЧКА ВХОДА: реализация разбита на пакет videoapp/
(см. docstring пакета). Напрямую здесь определены только те функции,
которые юнит-тесты читают/патчат через module-атрибуты app.*:

    app.st, app._param_str, app.capture_utm, app.utm_query, app.utm_extra,
    app.with_utm, app.validate_phone, app.sanitize_phone,
    app.area_to_rank, app._segment_table,

плюс реэкспорт констант (FEATURES_PATH, MODEL_PATH, BACKEND_URL и пр.),
на которые CODE/tests/инструменты подразумевают как на атрибуты app.
"""

import os
import sys
from urllib.parse import quote_plus

# Streamlit Cloud запускает «streamlit run app.py» из frontend/, но при других
# способах запуска каталог app.py может не попасть в sys.path — добавим его
# сами. Это же разрешает import videoapp и import analytics в подмодулях.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import streamlit as st  # noqa: E402  (атрибут app.st патчат тесты — обязан быть тут)

# ---------------------------------------------------------------------------
# UTM-хелперы (контракт тестов: определения живут в app и читают st модуля app)
# ---------------------------------------------------------------------------
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")


def _param_str(val) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, (list, tuple)) and val:
        return str(val[0])
    return str(val or "")


def capture_utm() -> dict[str, str]:
    """Читает UTM из query-параметров и кэширует в session_state на сессию."""
    try:
        if "utm" in st.session_state:
            return st.session_state["utm"]
    except Exception:
        return {}
    utm: dict[str, str] = {}
    try:
        qp = st.query_params
        for k in UTM_KEYS:
            v = qp.get(k)
            if v is not None and str(v):
                utm[k] = _param_str(v)
    except Exception:
        utm = {}
    try:
        st.session_state["utm"] = utm
    except Exception:
        pass
    return utm


def utm_query(extra: dict | None = None) -> str:
    """Query-строка из сохранённых UTM (+ переопределения, напр. utm_content=вариант)."""
    try:
        utm = dict(st.session_state.get("utm", {}))
    except Exception:
        utm = {}
    for k, v in (extra or {}).items():
        if v:
            utm[k] = str(v)
    return "&".join(f"{k}={quote_plus(str(v))}" for k, v in utm.items() if str(v))


def utm_extra() -> str:
    """Часть extra для событий аналитики в виде 'utm_source=...; utm_campaign=...'."""
    try:
        utm = dict(st.session_state.get("utm", {}))
    except Exception:
        utm = {}
    parts = [f"{k}={v}" for k, v in utm.items() if str(v)]
    return ("; " + "; ".join(parts)) if parts else ""


def with_utm(url: str, extra: dict | None = None) -> str:
    """Добавляет UTM к URL (или добавляет query даже к пустому url)."""
    q = utm_query(extra)
    if not q:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{q}"


# ---------------------------------------------------------------------------
# ВАЛИДАЦИЯ ТЕЛЕФОНА (контракт тестов: определения в app)
# ---------------------------------------------------------------------------
def validate_phone(phone: str) -> bool:
    """Проверяет, что телефон — валидный российский номер."""
    if not phone or not phone.strip():
        return False
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        return digits[0] == "9"
    if len(digits) == 11:
        return digits[0] in ("7", "8") and digits[1] == "9"
    return False


PHONE_ALLOWED_CHARS = set("0123456789+ ()-")


def sanitize_phone(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch in PHONE_ALLOWED_CHARS)


# ---------------------------------------------------------------------------
# РАНГ ПЛОЩАДИ (контракт тестов: определение в app)
# ---------------------------------------------------------------------------
def area_to_rank(area: float | None) -> int:
    if area is None or not isinstance(area, (int, float)):
        return 0
    if 20 <= area < 30:
        return 1
    elif 30 <= area < 40:
        return 2
    elif 40 <= area < 50:
        return 3
    elif 50 <= area < 60:
        return 4
    elif 60 <= area < 70:
        return 5
    elif 70 <= area < 80:
        return 6
    elif area >= 80:
        return 7
    return 0


# ---------------------------------------------------------------------------
# Сегменты ролика (контракт тестов: имя app._segment_table остаётся в app)
# ---------------------------------------------------------------------------
def _segment_table(ranked_factors: list | None) -> list:
    """Возвращает список сегментов ролика: [{name, start, dur}] в порядке
    воспроизведения. Первый сегмент — общий вид, далее выбранные факторы
    (стандартная длительность по категории).

    Тонкая обёртка: реализация живёт в videoapp.video_views.segment_table,
    но само имя обязано остаться атрибутом app (его вызывает юнит-тест)."""
    from videoapp.video_views import segment_table

    return segment_table(ranked_factors)


from videoapp.features import GROUP_DEFS  # noqa: E402

# ---------------------------------------------------------------------------
# Реэкспорт констант и словарей анкеты (модульные атрибуты app.*)
# ---------------------------------------------------------------------------

# Историческое имя словаря групп факторов, сохранено для совместимости.
GROUPS = GROUP_DEFS


# ---------------------------------------------------------------------------
# Точка входа: главный сценарий живёт в videoapp.flow
# ---------------------------------------------------------------------------
from videoapp.flow import main  # noqa: E402

if __name__ == "__main__":
    main()
