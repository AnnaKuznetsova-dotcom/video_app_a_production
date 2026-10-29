"""Графики Open Design: важность факторов / факторный анализ (SHAP-водопад) /
сравнение с ближайшим конкурентом, хронометраж этапов генерации."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from videoapp.features import GROUP_DEFS, compute_compare, local_signed_group_shap
from videoapp.questionnaire import QUESTIONNAIRE_MAP
from videoapp.theme import _feature_label


# ---------------------------------------------------------------------------
# ГРАФИКИ Open Design (важность / факторный анализ / сравнение)
# ---------------------------------------------------------------------------
def _render_importance_rows(items: list[tuple]) -> str:
    items = sorted(items, key=lambda kv: -kv[1])
    maxv = max((v for _, v in items), default=0.0)
    maxv = maxv if maxv > 0 else 1.0
    rows = []
    for i, (label, v) in enumerate(items):
        pct = round(v / maxv * 100)
        rows.append(
            f'<div class="k-shap-row"><div class="k-shap-label">{label}</div>'
            f'<div class="k-shap-track"><div class="k-shap-bar{"" if i < 4 else " low"}" '
            f'style="width:{pct}%"></div></div>'
            f'<div class="k-shap-value">{pct}%</div></div>'
        )
    return "".join(rows)


def _importance_items(shap_values: list | None, local_rows: list[dict] | None) -> list[tuple]:
    if local_rows:
        return [(r["label"], r["magnitude"]) for r in local_rows]
    items = []
    for item in shap_values or []:
        try:
            v = float(item.get("value", 0))
        except (TypeError, ValueError):
            v = 0.0
        items.append((_feature_label(item.get("name", "")), v))
    return items


def _waterfall_fig(rows_signed):
    """SHAP-водопад в горизонтальной ориентации (как принято у shap waterfall)."""
    if not rows_signed:
        return None
    items = sorted(rows_signed, key=lambda r: -abs(r["signed"]))
    items = [r for r in items if abs(r["signed"]) > 1e-9]
    if not items:
        return None
    fig = go.Figure(
        go.Waterfall(
            orientation="h",
            measure=["relative"] * len(items),
            y=[r["label"] for r in items][::-1],
            x=[r["signed"] for r in items][::-1],
            connector={"line": {"color": "#acafb4", "width": 1.5, "dash": "dot"}},
            increasing={"marker": {"color": "#168e38"}},
            decreasing={"marker": {"color": "#d96667"}},
            totals={"marker": {"color": "#26512d"}},
            hoverinfo="x+y",
        )
    )
    fig.update_layout(
        height=max(300, 44 * len(items) + 60),
        margin={"l": 10, "r": 10, "t": 8, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"size": 12, "color": "#373737"},
        showlegend=False,
        xaxis={"gridcolor": "#e7ebf0", "zerolinecolor": "#acafb4"},
        yaxis={"gridcolor": "#e7ebf0"},
    )
    return fig


def _p50_p95(vals):
    arr = np.array([v for v in vals if v > 0], dtype=float)
    if arr.size == 0:
        return None, None
    return int(np.percentile(arr, 50)), int(np.percentile(arr, 95))


_STAGE_KEYS = ["preprocess", "predict", "model_load"]


def imp_items_sorted(items):
    return sorted(items, key=lambda kv: -kv[1])


def _render_analytics(data):
    """Открытие result-блока: «Что повлияло на выбор» + «Факторный анализ»."""
    shap_values = data.get("shap_values") or []
    vector = st.session_state.get("vector")
    local_rows = local_signed_group_shap(vector, klass=data.get("klass")) if vector else None

    imp_items = _importance_items(shap_values, local_rows)
    bars_html = _render_importance_rows(imp_items_sorted(imp_items))

    with st.container():
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown(
                '<div class="k-shap-card"><h3>Что повлияло на выбор</h3>'
                '<p class="sub">График важности факторов: чем длиннее столбец, тем сильнее '
                "этот признак повлиял на решение ИИ.</p>" + bars_html + "</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                '<div class="k-shap-card"><h3>Факторный анализ</h3>'
                '<p class="sub">Детали: каждый признак либо приближает решение к посёлку '
                "(зелёный, идёт вверх от «Базовый сценарий»), либо отдаляет (красный).</p></div>",
                unsafe_allow_html=True,
            )
            fig = _waterfall_fig(local_rows)
            if fig is not None:
                st.plotly_chart(
                    fig, width="stretch", config={"displayModeBar": False}, key="wf_chart"
                )
            else:
                st.caption(
                    "Детальный знаковый вклад пока недоступен (модель не загружена локально)."
                )


def render_stage_timings(data):
    """График этапов хронометража генерации + p50/p95 cold/warm по истории сессии.

    В video_app_a SHAP-extraction нет — этап SHAP в график не включается.
    Бэкенд A отдаёт stage_timing_ms (в b/c ключ называется timings_ms).
    """

    def _remember(data):
        timings = data.get("timings_ms") or data.get("stage_timing_ms") or {}
        job_id = data.get("job_id") or ""
        if not timings or not job_id:
            return
        seen = st.session_state.setdefault("timings_seen", set())
        if job_id in seen:
            return
        seen.add(job_id)
        rec = {
            "cold": bool(data.get("is_cold")),
            "latency": int(st.session_state.get("latency_ms") or timings.get("total") or 0),
        }
        for key in _STAGE_KEYS:
            rec[key] = int(timings.get(key) or 0)
        hist = list(st.session_state.get("timings_history") or [])
        hist.append(rec)
        st.session_state["timings_history"] = hist[-12:]

    timings = data.get("timings_ms") or data.get("stage_timing_ms") or {}
    if not timings:
        st.caption("Хронометраж недоступен: бэкенд не вернул timings этапа.")
        return
    _remember(data)

    labels = {
        "preprocess": "Preprocessing",
        "predict": "Prediction",
        "model_load": "Загрузка модели (холодный запуск)",
    }
    values = [int(timings.get(k) or 0) for k in _STAGE_KEYS]
    with st.expander("Хронометраж этапов генерации (диагностика)", expanded=False):
        st.bar_chart(
            pd.DataFrame({"мс": values}, index=[labels[k] for k in _STAGE_KEYS]), height=260
        )

        hist = list(st.session_state.get("timings_history") or [])
        rows = []
        for name, cold_flag in (("Холодный", True), ("Тёплый", False)):
            vals = [h.get("latency", 0) for h in hist if bool(h.get("cold")) == cold_flag]
            p50, p95 = _p50_p95(vals)
            if p50 is None:
                continue
            rows.append({"Замер": f"{name} (n={len(vals)})", "p50, мс": p50, "p95, мс": p95})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True)
            st.caption(
                "Пакет замеров: последние 12 генераций сессии. "
                "Холодный — первый вызов после старта контейнера; "
                "latency измеряется на фронте (клиент → сервер)."
            )
        else:
            st.caption("Замеры накапливаются в сессии — сгенерируйте ролик ещё раз.")


def _render_compare(vector: dict[str, int]):
    """«Сравнение с ближайшим конкурентом»: модель локально, конкурент = 2-й класс по вероятности."""
    compare = compute_compare(vector) if vector else None
    if not compare:
        return
    wmap = {r["key"]: r for r in compare["rows_win"]}
    rmap = {r["key"]: r for r in compare["rows_run"]}
    rows_html = ""
    for g in GROUP_DEFS:
        w = float(wmap.get(g["key"], {}).get("magnitude", 0.0))
        r = float(rmap.get(g["key"], {}).get("magnitude", 0.0))
        tot = (w + r) or 1.0
        wp = round(w / tot * 50)
        rp = round(r / tot * 50)
        rows_html += (
            '<div class="k-shap-row"><div class="k-cmp-label">'
            f'{g["label"]} ({w:.3f})</div>'
            '<div class="k-cmp-track"><div class="k-cmp-center"></div>'
            f'<div class="k-cmp-bar winner" style="width:{wp}%"></div>'
            f'<div class="k-cmp-bar runner" style="width:{rp}%"></div></div>'
            '<div class="k-cmp-label">'
            f'{g["label"]} ({r:.3f})</div></div>'
        )
    st.markdown(
        '<div class="k-shap-card" style="margin-top:18px"><h3>Сравнение с ближайшим конкурентом</h3>'
        '<p class="sub">Сравнение факторов выбранного посёлка и конкурента.</p>'
        '<div style="display:flex;justify-content:space-between;margin-bottom:8px">'
        f'<span class="k-cmp-name-w">{compare["winner_label"]}</span>'
        f'<span class="k-cmp-name-r">{compare["runner_label"]}</span></div>'
        f"{rows_html}</div>",
        unsafe_allow_html=True,
    )


def _ranked_labels(ranked) -> list[str]:
    """Компактные читаемые подписи топ-факторов для чипов «Важно для вас»."""
    labels = []
    for f in ranked[:3]:
        for g in GROUP_DEFS:
            if str(f).startswith(g["prefix"]) or (
                g.get("alt_prefix") and str(f).startswith(g["alt_prefix"])
            ):
                labels.append(g["label"])
                break
        else:
            labels.append(_feature_label(f))
    return labels


def _clear_answers():
    for item in QUESTIONNAIRE_MAP:
        st.session_state.pop(f"q_{item['feature_prefix']}", None)
    st.session_state.pop("q_area", None)
