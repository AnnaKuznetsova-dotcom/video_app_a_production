"""Главный сценарий приложения main(): сборка страницы от лендинга до заявки."""

import os
import time

import requests
import streamlit as st
from videoapp.features import build_feature_vector
from videoapp.questionnaire import (
    QUESTIONNAIRE_MAP,
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
from videoapp.shap_views import (
    _clear_answers,
    _ranked_labels,
    _render_analytics,
    _render_compare,
    render_stage_timings,
)
from videoapp.theme import CSS, _hourglass_html, asset
from videoapp.video_views import _render_video

import analytics


# ---------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="KASKAD · Персональный видеокаталог", page_icon="🏡", layout="wide"
    )
    st.markdown(CSS, unsafe_allow_html=True)

    _hero_block_fragment()

    # Регистрируем новый визит (для бизнес-метрик CTR/CR/TTL).
    if "tlx_session_logged" not in st.session_state:
        analytics.log_session()
        st.session_state["tlx_session_logged"] = True

    if not BACKEND_URL or BACKEND_URL == "http://localhost:8080":
        st.warning("BACKEND_URL не задан. Задайте его в Secrets или переменной окружения.")

    # Проверка бэкенда — не чаще, чем раз в HEALTH_CHECK_TTL секунд.
    now = time.time()
    if st.session_state.get("health_ts", 0) + HEALTH_CHECK_TTL > now:
        backend_ok = st.session_state.get("backend_ok", False)
    else:
        try:
            r = requests.get(f"{BACKEND_URL}/health", timeout=HEALTH_CHECK_TIMEOUT)
            backend_ok = r.status_code == 200 and r.json().get("status") == "ok"
        except Exception:
            backend_ok = False
        st.session_state["backend_ok"] = backend_ok
        st.session_state["health_ts"] = now

    # ---- ОПРОСНИК (Open Design дизайн + бегунок) ----
    st.markdown(
        """
<div class="k-section-title">
  <h2>Пройдите анкету</h2>
  <span class="underline"></span>
  <p>Ответьте на 9 вопросов — и ИИ подготовит персональную подборку.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown('<div class="k-quiz-shell">', unsafe_allow_html=True)
        _questionnaire_fragment()
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.get("generating"):
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
                payload = {"features": vector, "explicit_factors": []}
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
                    extra=f"latency_ms={latency_ms}; settlement={data.get('settlement','')}",
                )
                st.rerun()
            except Exception as exc:
                st.session_state["generating"] = False
                st.session_state["error"] = str(exc)
                analytics.log_event("error_record", extra=f"err={exc}")
                st.error(f"Не удалось создать ролик: {exc}")

    # ---- ПОКАЗ РЕЗУЛЬТАТА (Open Design) ----
    if "result" in st.session_state:
        # UTM-хелпер живёт в app.py (контракт тестов app.*) — ленивый импорт
        # (анти-цикл: app → videoapp.flow → videoapp.*).
        from app import utm_extra  # noqa: PLC0415

        data = st.session_state["result"]
        variation = data.get("variant") or st.session_state.get("variant") or ""
        settlement_raw = data.get("settlement", "—")
        settlement_name = SETTLEMENT_NAMES.get(settlement_raw, settlement_raw)
        selected_project = project_by_settlement(settlement_raw) or {}
        proj_img = selected_project.get("img") or SETTLEMENT_IMG.get(
            settlement_raw, "kaskad_park_1.jpg"
        )
        _proj_meta = (
            selected_project.get("distance", "") + " · " + selected_project.get("highway", "")
        ).strip(" ·")
        feats = ", ".join((selected_project.get("features") or [])[:4])
        _proj_price = selected_project.get("price", "")
        proj_url = selected_project.get("url", "")

        st.markdown(
            """
<div class="k-section-title">
  <h2>Ваш персональный результат</h2>
  <span class="underline"></span>
  <p>ИИ подобрал посёлок, объяснил логику выбора и смонтировал видео.</p>
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
                pretty = {
                    "безопасность": "Безопасность",
                    "инфраструктура": "Инфраструктура",
                    "контингент": "Контингент",
                    "природа и экология": "Природа и экология",
                    "транспортная доступность": "Транспортная доступность",
                    "иное": "Особые пожелания",
                }
                chosen_vals = []
                for item in QUESTIONNAIRE_MAP:
                    v = st.session_state.get(f"q_{item['feature_prefix']}")
                    if v:
                        chosen_vals.append(pretty.get(v, v))
                chips = "".join(f'<span class="k-chip">{v}</span>' for v in chosen_vals)
                st.markdown(
                    f"""<div class="k-result-hero">
                    <h2>Лучший выбор — <span class="village">{settlement_name}</span></h2>
                    <p>Особенности: {feats}</p></div>""",
                    unsafe_allow_html=True,
                )
                if chips:
                    st.markdown(
                        f'<div class="k-chips" style="margin:14px 0 0">{chips}</div>',
                        unsafe_allow_html=True,
                    )
                if proj_url:
                    st.markdown(f"[Открыть сайт посёлка]({proj_url})")

        # ---- ПЕРСОНАЛЬНОЕ ВИДЕО (+ тег «Важно для вас») ----
        ranked = data.get("ranked_factors") or []
        if ranked:
            st.html('<span class="k-video-tag">Важно для вас</span>')
            st.html(
                '<div class="k-imp-wrap">'
                + "".join(
                    f'<span class="k-chip-imp">{lbl}</span>' for lbl in _ranked_labels(ranked)
                )
                + "</div>"
            )

        video_url = data.get("video_url")
        if video_url:
            _render_video(
                video_url,
                ranked_factors=data.get("ranked_factors"),
                variant=variation,
                utm=utm_extra(),
            )
            if not st.session_state.get("video_shown_logged"):
                try:
                    analytics.log_video_shown(video_url, variant=variation, utm=utm_extra())
                except Exception:
                    pass
                st.session_state["video_shown_logged"] = True
        else:
            st.info("Ссылка на ролик не получена.")

        # ---- ГРАФИКИ ----
        _render_analytics(data)
        render_stage_timings(data)
        _render_compare(st.session_state.get("vector"))

        # Отчёт «Фактор / Вклад SHAP / Длительность» перенесён в tools/charts
        # (файл reports/factor_report.csv, генерируется скриптом
        # tools/report_factor_csv.py) — в приложении он больше не выводится.

        # ---- CTA ----
        st.markdown(
            """<div class="k-cta">
            <h2>Хотите увидеть посёлок вживую?</h2>
            <p>Оставьте заявку — менеджер группы Каскад организует персональный показ и расскажет об условиях покупки.</p></div>""",
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

    if "error" in st.session_state:
        st.error(st.session_state["error"])

    st.markdown(
        """<div class="k-footer">© 2026 Группа Каскад. Прототип ИИ-сервиса для демонстрации концепции.</div>""",
        unsafe_allow_html=True,
    )
