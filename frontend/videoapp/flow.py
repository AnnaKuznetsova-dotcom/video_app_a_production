"""Главный сценарий приложения main(): сборка страницы от лендинга до заявки."""

import os
import time

import requests
import streamlit as st
from videoapp.features import build_feature_vector
from videoapp.questionnaire import (
    QUESTIONNAIRE_MAP,
    _clear_answers,
    _clear_result,
    _hero_block_fragment,
    _questionnaire_fragment,
    render_lead_form,
)
from videoapp.settings import (
    BACKEND_URL,
    HEALTH_CHECK_TIMEOUT,
    HEALTH_CHECK_TTL,
    SETTLEMENT_IMG,
    SETTLEMENT_NAMES,
    project_by_settlement,
)
from videoapp.theme import CSS, _hourglass_html, asset
from videoapp.video_views import _render_video, render_stage_timings

import analytics


# ---------------------------------------------------------------------------
# ЭТАП 1: страница и анкета
# ---------------------------------------------------------------------------
def _setup_page():
    st.set_page_config(page_title="KASKAD · Видеокаталог посёлков", page_icon="🏡", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    _hero_block_fragment()

    # Регистрируем новый визит (для бизнес-метрик CTR/CR/TTL).
    if "tlx_session_logged" not in st.session_state:
        analytics.log_session()
        st.session_state["tlx_session_logged"] = True

    if not BACKEND_URL or BACKEND_URL == "http://localhost:8080":
        st.warning("BACKEND_URL не задан. Задайте его в Secrets или переменной окружения.")


def _backend_ok() -> bool:
    """Проверка бэкенда — не чаще, чем раз в HEALTH_CHECK_TTL секунд."""
    now = time.time()
    if st.session_state.get("health_ts", 0) + HEALTH_CHECK_TTL > now:
        return st.session_state.get("backend_ok", False)
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=HEALTH_CHECK_TIMEOUT)
        ok = r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        ok = False
    st.session_state["backend_ok"] = ok
    st.session_state["health_ts"] = now
    return ok


def _render_questionnaire():
    st.markdown(
        """
<div class="k-section-title">
  <h2>Пройдите анкету</h2>
  <span class="underline"></span>
  <p>Ответьте на 9 вопросов — и ИИ подберёт посёлок с готовым видеороликом.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown('<div class="k-quiz-shell">', unsafe_allow_html=True)
        _questionnaire_fragment()
        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# ЭТАП 2: запрос на генерацию ролика
# ---------------------------------------------------------------------------
def _handle_generation():
    st.markdown(_hourglass_html(), unsafe_allow_html=True)
    with st.spinner("Искусственный интеллект подбирает идеальный дом для Вас и Вашей семьи..."):
        try:
            ans = {}
            for item in QUESTIONNAIRE_MAP:
                prefix = item["feature_prefix"]
                v = st.session_state.get(f"q_{prefix}")
                if v is not None:
                    ans[prefix] = v
            area = st.session_state.get("q_area")
            vector = build_feature_vector(ans, area)
            payload = {"features": vector}
            start = time.monotonic()
            resp = requests.post(f"{BACKEND_URL}/generate/", json=payload, timeout=120)
            latency_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()
            st.session_state["generating"] = False
            st.session_state["result"] = data
            st.session_state["vector"] = vector
            st.session_state["latency_ms"] = latency_ms
            analytics.log_event(
                "latency_record",
                extra=f"latency_ms={latency_ms}; settlement={data.get('settlement', '')}",
            )
            st.rerun()
        except Exception as exc:
            st.session_state["generating"] = False
            st.session_state["error"] = str(exc)
            analytics.log_event("error_record", extra=f"err={exc}")
            st.error(f"Не удалось создать ролик: {exc}")


# ---------------------------------------------------------------------------
# ЭТАП 3: показ результата (подбор → ролик → заявка)
# ---------------------------------------------------------------------------
def _result_header(settlement_name: str, feats: str, proj_img: str, proj_url: str):
    st.markdown(
        """
<div class="k-section-title">
  <h2>Ваш результат</h2>
  <span class="underline"></span>
  <p>ИИ подобрал посёлок и подготовил видеоролик.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.container():
        c_img, c_txt = st.columns([0.5, 0.5], gap="large")
        with c_img:
            if os.path.exists(asset(proj_img)):
                st.image(asset(proj_img))
        with c_txt:
            st.markdown(
                f"""<div class="k-result-hero">
                <h2>Лучший выбор — <span class="village">{settlement_name}</span></h2>
                <p>Особенности: {feats}</p></div>""",
                unsafe_allow_html=True,
            )
            if proj_url:
                st.markdown(f"[Открыть сайт посёлка]({proj_url})")


def _video_block(data: dict, variation: str):
    video_url = data.get("video_url")
    if not video_url:
        st.info("Ссылка на ролик не получена.")
        return
    _render_video(video_url, variant=variation, utm=_utm_extra())
    if not st.session_state.get("video_shown_logged"):
        try:
            analytics.log_video_shown(video_url, variant=variation, utm=_utm_extra())
        except Exception:
            pass
        st.session_state["video_shown_logged"] = True
    render_stage_timings(data)


def _cta_block(settlement_name: str):
    st.markdown(
        """<div class="k-cta">
        <h2>Хотите увидеть посёлок вживую?</h2>
        <p>Оставьте заявку — менеджер группы Каскад организует показ и расскажет об условиях покупки.</p></div>""",
        unsafe_allow_html=True,
    )
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Записаться на показ", type="primary", width="stretch", key="cta_book"):
            st.session_state["show_lead_form"] = True
            st.rerun()
    with b2:
        if st.button("Пройти анкету заново", width="stretch", key="restart_quiz"):
            _clear_result()
            _clear_answers()
            st.session_state["show_lead_form"] = False
            st.rerun()

    if st.session_state.get("show_lead_form"):
        render_lead_form(settlement_name)


def _utm_extra() -> str:
    # UTM-хелпер живёт в app.py (контракт тестов app.*) — ленивый импорт
    # (анти-цикл: app → videoapp.flow → videoapp.*).
    from app import utm_extra  # noqa: PLC0415

    return utm_extra()


def _result_block():
    data = st.session_state["result"]
    variation = data.get("variant") or st.session_state.get("variant") or ""
    settlement_raw = data.get("settlement", "—")
    settlement_name = SETTLEMENT_NAMES.get(settlement_raw, settlement_raw)
    selected_project = project_by_settlement(settlement_raw) or {}
    proj_img = selected_project.get("img") or SETTLEMENT_IMG.get(
        settlement_raw, "kaskad_park_1.jpg"
    )
    feats = ", ".join((selected_project.get("features") or [])[:4])
    proj_url = selected_project.get("url", "")

    _result_header(settlement_name, feats, proj_img, proj_url)
    _video_block(data, variation)
    _cta_block(settlement_name)


# ---------------------------------------------------------------------------
def main():
    _setup_page()
    _backend_ok()
    _render_questionnaire()

    if st.session_state.get("generating"):
        _handle_generation()

    if "result" in st.session_state:
        _result_block()

    if "error" in st.session_state:
        st.error(st.session_state["error"])

    st.markdown(
        """<div class="k-footer">© 2026 Группа Каскад. Прототип ИИ-сервиса для демонстрации концепции.</div>""",
        unsafe_allow_html=True,
    )
