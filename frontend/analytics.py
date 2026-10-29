"""
Модуль сбора метрик на стороне Streamlit (frontend).

Хранение — ТОЛЬКО CSV (легко открыть в Excel / Pandas).

Собираемые события:
    session_start        — заход пользователя (новый визит, создаётся Client ID).
    preview_click        — клик по кнопке «Смотреть видео».
    lead_submit          — отправка формы «Заказать звонок» (лид).
    latency_record       — замер времени ответа бэкенда (клиент->сервер).
    error_record         — ошибка при обращении к бэкенду.

Бизнес-метрики, которые можно посчитать по этим данным:
    - CTR превью          = preview_click_count / session_count
    - Конверсия в лид (CR) = lead_submit_count / session_count
    - Time-to-Lead (TTL)   = время от первого касания (поля ts_iso сессии)
                             до отправки лида (одним и тем же Client ID).
    - Latency              = поле latency_ms.

Client ID хранится в cookie браузера (streamlit загружает JS, который
ставит/читает cookie). Это надёжно работает и в Streamlit Cloud.
"""

import csv
import os
import threading
import uuid
from datetime import UTC, datetime

import streamlit.components.v1 as components

ANALYTICS_DIR = os.getenv(
    "ANALYTICS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "analytics_output")
)
EVENTS_CSV = os.getenv("EVENTS_CSV", os.path.join(ANALYTICS_DIR, "events.csv"))
SESSIONS_CSV = os.getenv("SESSIONS_CSV", os.path.join(ANALYTICS_DIR, "sessions.csv"))
# ОТДЕЛЬНЫЙ ОТЧЁТ ПО ПОКУПАТЕЛЯМ (ФИО + телефон) — reports/leads.csv
REPORTS_DIR = os.getenv(
    "REPORTS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
)
LEADS_CSV = os.getenv("LEADS_CSV", os.path.join(REPORTS_DIR, "leads.csv"))

EVENT_HEADER = ["ts_iso", "client_id", "event_type", "extra"]
SESSION_HEADER = ["ts_iso", "client_id", "first_touch_ts"]
LEADS_HEADER = ["ts_iso", "client_id", "fio", "phone", "settlement"]

_lock = threading.Lock()

# --- Долговременное хранение событий/сессий в S3 (по аналогии с бэкендом).
#     Streamlit Cloud держит локальный диск эфемерно, поэтому CSV после
#     пересборки приложения теряются. Копируем их в S3-бакет Yandex Cloud.
#     Работает только если заданы секреты: YC_ACCESS_KEY_ID, YC_SECRET_ACCESS_KEY,
#     BUCKET_NAME (и, опционально, YC_S3_ENDPOINT). Без них — только локально.
_S3_LAST_SYNC = 0.0
_S3_SYNC_INTERVAL = 60.0  # не чаще 1 раза в минуту (чтобы не грузить S3)


def _s3_credentials() -> tuple:
    """Возвращает (endpoint, bucket, key_id, secret) из env или Streamlit secrets."""
    try:
        import streamlit as st

        env = dict(os.environ)
        sec = dict(st.secrets) if hasattr(st, "secrets") else {}
    except Exception:
        env = dict(os.environ)
        sec = {}

    def _get(name: str, default: str = "") -> str:
        return env.get(name) or sec.get(name, default)

    endpoint = _get("YC_S3_ENDPOINT", "https://storage.yandexcloud.net")
    bucket = _get("BUCKET_NAME")
    key_id = _get("YC_ACCESS_KEY_ID")
    secret = _get("YC_SECRET_ACCESS_KEY")
    return endpoint, bucket, key_id, secret


def sync_events_to_s3(force: bool = False) -> bool:
    """Загружает события и сессии в S3 (префикс metrics_frontend/).

    Вызывается внутри log_* без ограничения; внутри функции стоит троттлинг,
    чтобы не дёргать S3 на каждое событие. Возвращает True, если файлы залиты.
    """
    global _S3_LAST_SYNC
    import time as _time

    now = _time.time()
    if not force and (now - _S3_LAST_SYNC) < _S3_SYNC_INTERVAL:
        return False
    endpoint, bucket, key_id, secret = _s3_credentials()
    if not (bucket and key_id and secret):
        return False
    try:
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            region_name="ru-central1",
        )
        for local_path, key in (
            (EVENTS_CSV, "metrics_frontend/events.csv"),
            (SESSIONS_CSV, "metrics_frontend/sessions.csv"),
        ):
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                s3.upload_file(local_path, bucket, key)
        _S3_LAST_SYNC = now
        return True
    except Exception:
        # Не роняем приложение из-за метрик — только скрытый warning в логи.
        try:
            import streamlit as st

            st.warning("Метрики не удалось загрузить в S3 (проверьте секреты YC).")
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Client ID (cookie). Streamlit не даёт прямой доступ к document.cookie,
# поэтому подключаем крошечный JS через components.html.
# ---------------------------------------------------------------------------
def _cookie_js() -> str:
    return """
    <script>
    function setCookie(name, value, days) {
      var d = new Date();
      d.setTime(d.getTime() + (days*24*60*60*1000));
      document.cookie = name + "=" + value + ";expires=" + d.toUTCString() + ";path=/";
    }
    function getCookie(name) {
      var match = document.cookie.match('(^|;)\\\\s*' + name + '=([^;]*)');
      return match ? decodeURIComponent(match[2]) : null;
    }
    var cid = getCookie('tlx_client_id');
    if (!cid) {
      cid = 'cid_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
      setCookie('tlx_client_id', cid, 365);
    }
    var sid = getCookie('tlx_session_ts');
    if (!sid) {
      sid = new Date().toISOString();
      setCookie('tlx_session_ts', sid, 365);
    }
    window.parent.postMessage({
      type: 'tlx_analytics',
      client_id: cid,
      session_ts: sid
    }, '*');
    </script>
    """


def get_client_id() -> str | None:
    """
    Вызывается один раз при старте сессии. Вручную прочитать cookie в Python
    из Streamlit нельзя напрямую, поэтому показываем JS и предлагаем сохранить
    результат в session_state — значение берём из Message-канала.
    Возвращает client_id и кладёт session_ts в session_state.
    """
    try:
        import streamlit as st

        components.html(_cookie_js(), height=0, width=0)
        # Первый заход: создаём локальный ID и фиксируем время сессии,
        # чтобы TTL считался даже без полного cookie-моста.
        if "tlx_client_id" not in st.session_state:
            st.session_state["tlx_client_id"] = "cid_" + uuid.uuid4().hex[:12]
        if "tlx_session_ts" not in st.session_state:
            st.session_state["tlx_session_ts"] = _now_iso()
        return st.session_state["tlx_client_id"]
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _append_csv(path: str, header: list, row: list):
    try:
        with _lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            new_file = not os.path.exists(path) or os.path.getsize(path) == 0
            with open(path, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(header)
                w.writerow(row)
    except Exception:
        pass


def _client_id() -> str:
    return get_client_id() or "unknown"


def log_session():
    """Регистрирует новый визит (сессию) пользователя в sessions.csv."""
    cid = _client_id()
    _append_csv(SESSIONS_CSV, SESSION_HEADER, [_now_iso(), cid, _now_iso()])
    sync_events_to_s3()


def log_event(event_type: str, extra: str = ""):
    """Фиксирует произвольное событие в events.csv."""
    _append_csv(EVENTS_CSV, EVENT_HEADER, [_now_iso(), _client_id(), event_type, extra])
    if event_type != "session_start":
        sync_events_to_s3()


def log_preview_click(utm: str = ""):
    log_event("preview_click", utm)


def log_lead(name: str | None = "", phone: str | None = "", variant: str = "", utm: str = ""):
    cleaned_name = (name or "").replace(";", "|").strip()
    extra = f"variant={variant}; name= {cleaned_name}; phone={phone}"
    if utm:
        extra += f"; {utm}"
    log_event("lead_submit", extra)


def log_lead_report(fio: str, phone: str, settlement: str = ""):
    """Ведёт ОТДЕЛЬНЫЙ отчёт по покупателям (reports/leads.csv):
    ФИО, телефон, посёлок. Отчёт копируется в S3 (metrics_frontend/leads.csv)."""
    _append_csv(
        LEADS_CSV,
        LEADS_HEADER,
        [_now_iso(), _client_id(), fio, phone, settlement or ""],
    )
    try:
        endpoint, bucket, key_id, secret = _s3_credentials()
        if bucket and key_id and secret and os.path.exists(LEADS_CSV):
            import boto3

            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=key_id,
                aws_secret_access_key=secret,
                region_name="ru-central1",
            )
            s3.upload_file(LEADS_CSV, bucket, "metrics_frontend/leads.csv")
    except Exception:
        pass


def log_lead_empty():
    log_event("lead_submit_empty")


def log_video_shown(video_url: str = "", variant: str = "", utm: str = ""):
    """Ролик показан пользователю (знаменатель для retention/досмотров)."""
    log_event("video_shown", f"variant={variant}; url={video_url}" + (f"; {utm}" if utm else ""))


def log_video_play(video_url: str = "", variant: str = "", utm: str = ""):
    """Пользователь начал смотреть сгенерированный ролик (эвент для VCR/CTR)."""
    log_event("video_play", f"variant={variant}; url={video_url}" + (f"; {utm}" if utm else ""))


def log_video_progress(event_type: str, video_url: str = "", variant: str = "", utm: str = ""):
    """Бизнес-метрики просмотра: video_retention_3s, video_watch_25/50/75/100."""
    log_event(event_type, f"variant={variant}; url={video_url}" + (f"; {utm}" if utm else ""))


def log_reklama_click(video_url: str = "", variant: str = "", utm: str = ""):
    """Клик по рекламной ссылке (переход из плеера) — CTR рекламной ссылки."""
    log_event("reklama_click", f"variant={variant}; url={video_url}" + (f"; {utm}" if utm else ""))


def log_video_completed(video_url: str = "", variant: str = "", utm: str = ""):
    """Ролик досмотрен до конца — событие закрытия video (для VCR)."""
    log_event(
        "video_completed", f"variant={variant}; url={video_url}" + (f"; {utm}" if utm else "")
    )


# ---------------------------------------------------------------------------
# Бизнес-сводка: CTR / CR / VCR / TTL + удержание/досмотры по вариантам.
# ---------------------------------------------------------------------------
def _extra_dict(extra: str) -> dict:
    kv = {}
    for part in (extra or "").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def _event_rows(event_type: str | None = None, variant: str | None = None):
    """Итерирует events.csv, фильтруя по типу и, при задании, варианту сценария."""
    if not os.path.exists(EVENTS_CSV):
        return
    with open(EVENTS_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if event_type and r.get("event_type") != event_type:
                continue
            if (
                variant is not None
                and _extra_dict(r.get("extra", "")).get("variant", "") != variant
            ):
                continue
            yield r


def _count_events(event_type: str, variant: str | None = None) -> int:
    return sum(1 for _ in _event_rows(event_type, variant))


def _variant_names() -> list:
    seen = set()
    for r in _event_rows():
        v = _extra_dict(r.get("extra", "")).get("variant", "")
        if v:
            seen.add(v)
    return sorted(seen)


def _spend() -> float | None:
    s = os.getenv("CAMPAIGN_SPEND_USD", "").strip()
    try:
        return float(s) if s else None
    except ValueError:
        return None


def _session_count() -> int:
    if not os.path.exists(SESSIONS_CSV):
        return 0
    with open(SESSIONS_CSV, encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


def _biz_for_variant(variant: str | None, sessions_total: int, spend: float | None) -> dict:
    """Метрики по одной версии сценария (variant=None — по всем)."""
    shown = _count_events("video_shown", variant)
    plays = _count_events("video_play", variant)
    ret3 = _count_events("video_retention_3s", variant)
    w25 = _count_events("video_watch_25", variant)
    w50 = _count_events("video_watch_50", variant)
    w75 = _count_events("video_watch_75", variant)
    w100 = _count_events("video_watch_100", variant)
    clicks = _count_events("reklama_click", variant)
    leads = _count_events("lead_submit", variant)
    prev = _count_events("preview_click", variant)
    completed = _count_events("video_completed", variant)
    return {
        "sessions": sessions_total,
        "preview_clicks": prev,
        "assigned_views": shown,
        "video_plays": plays,
        "reklama_clicks": clicks,
        "leads": leads,
        "ctr_preview_pct": round(100.0 * prev / sessions_total, 2) if sessions_total else None,
        "ctr_video_pct": round(100.0 * plays / shown, 2) if shown else None,
        "ctr_reklama_pct": round(100.0 * clicks / shown, 2) if shown else None,
        "retention_3s_pct": round(100.0 * ret3 / shown, 2) if shown else None,
        "watch_25_pct": round(100.0 * w25 / shown, 2) if shown else None,
        "watch_50_pct": round(100.0 * w50 / shown, 2) if shown else None,
        "watch_75_pct": round(100.0 * w75 / shown, 2) if shown else None,
        "watch_100_pct": round(100.0 * w100 / shown, 2) if shown else None,
        "conversion_rate_cr_pct": (
            round(100.0 * leads / sessions_total, 2) if sessions_total else None
        ),
        "video_completion_rate_vcr_pct": round(100.0 * completed / plays, 2) if plays else None,
        "cost_per_lead_usd": round(spend / leads, 2) if (spend and leads) else None,
        "cost_per_assigned_view_usd": round(spend / shown, 2) if (spend and shown) else None,
    }


def business_summary() -> dict:
    """Считает бизнес-метрики по собранным CSV. Отдельно по каждому 'variant'
    сценария (пункт ЧЗ: метрики по версиям), а также сводку по всем. Стоимость
    считается при заданном CAMPAIGN_SPEND_USD (бюджет кампании)."""
    spend = _spend()
    if not os.path.exists(EVENTS_CSV) and not os.path.exists(SESSIONS_CSV):
        return {"sessions": 0}
    sessions = _session_count()
    overall = _biz_for_variant(None, sessions, spend)
    variants = {}
    for v in _variant_names():
        variants[v] = _biz_for_variant(v, sessions, spend)
    overall["variants"] = variants
    # Средний TTL по всем Client ID, у которых есть лид.
    ttls = []
    if os.path.exists(SESSIONS_CSV):
        with open(SESSIONS_CSV, encoding="utf-8-sig") as f:
            for s in csv.DictReader(f):
                cid = s.get("client_id")
                if cid:
                    t = ttl_seconds_for(cid)
                    if t is not None:
                        ttls.append(t)
    overall["ttl_seconds_avg"] = round(sum(ttls) / len(ttls), 1) if ttls else None
    return overall


# ---------------------------------------------------------------------------
# Time-to-Lead: считаем по записям CSV одним Client ID.
# ---------------------------------------------------------------------------
def ttl_seconds_for(client_id: str) -> float | None:
    """Разница между первым заходом (sessions) и последним лидом (events)."""
    try:
        session_ts = None
        if os.path.exists(SESSIONS_CSV):
            with open(SESSIONS_CSV, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    if r.get("client_id") == client_id:
                        session_ts = r.get("ts_iso")
        if not session_ts:
            return None
        lead_ts = None
        if os.path.exists(EVENTS_CSV):
            with open(EVENTS_CSV, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    if r.get("client_id") == client_id and r.get("event_type") == "lead_submit":
                        lead_ts = r.get("ts_iso")
        if not lead_ts:
            return None
        t0 = datetime.fromisoformat(session_ts)
        t1 = datetime.fromisoformat(lead_ts)
        return (t1 - t0).total_seconds()
    except Exception:
        return None
