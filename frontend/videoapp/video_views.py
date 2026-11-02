"""Кастомный плеер со сбором метрик и таблица сегментов ролика.

Границы сегментов по умолчанию — см. theme._SEGMENT_DUR_S. В варианте A
ролик фиксированный по посёлку, поэтому сегмент обычно один («общий вид»);
таблица сегментов сохранена для совместимости плеера и метрик досмотра.

Имя `_segment_table` (в тонкой обёртке) обязано оставаться в app.py —
его вызывает юнит-тест app._segment_table(...)"""

import json

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from videoapp.settings import USE_CUSTOM_PLAYER
from videoapp.theme import _OVERALL_DUR_S, _SEGMENT_DUR_S

import analytics


def segment_table(ranked_factors: list | None) -> list:
    """Возвращает список сегментов ролика: [{name, start, dur}] в порядке
    воспроизведения. Первый сегмент — общий вид; далее (если ranked_factors
    задан) стандартные длительности по категории."""
    segs = [{"name": "общий вид", "start": 0, "dur": _OVERALL_DUR_S}]
    t = _OVERALL_DUR_S
    for f in ranked_factors or []:
        d = _SEGMENT_DUR_S.get("общий вид", 5)
        for key, dur in _SEGMENT_DUR_S.items():
            if key != "общий вид" and key in str(f):
                d = dur
                break
        segs.append({"name": str(f), "start": t, "dur": d})
        t += d
    return segs


def _esc(x) -> str:
    return (
        (x or "")
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_PLAYER_HTML = """
<div style="width:100%;border-radius:12px;overflow:hidden;background:#000;">
  <video id="kvideo" src="{src}" controls playsinline
         style="width:100%;height:auto;display:block;object-fit:contain;max-height:720px;background:#000;"
         preload="auto"></video>
  <a href="{reklam_href}" target="_blank" rel="noopener"
     style="display:block;text-align:center;padding:8px;color:#168e38;
            background:#fff;font-size:14px;text-decoration:none;"
     onclick="(function(){{ send('reklama_click', '{reklam_extra}'); }})(); return true;">
    Открыть рекламный ролик в новой вкладке ↗
  </a>
</div>
<script>
(function(){{
  var v = document.getElementById('kvideo');
  if (!v) return;
  var url = "{src}";
  var segs = {seg_json};
  var segWatch = new Array(segs.length).fill(0);
  var playLogged = false, completeLogged = false;
  var lastSent = null;
  var lastSec = null;
  var MAX = 240 * 60;   // защита: до 4 часов
  var flags = {{ret3:false, w25:false, w50:false, w75:false, w100:false}};

  function segIndex(sec) {{
    for (var i = segs.length - 1; i >= 0; i--) {{
      if (sec >= segs[i].start) return i;
    }}
    return 0;
  }}

  function send(event_type, extra) {{
    var msg = {{type: event_type, extra: (extra||'')}};
    var s = JSON.stringify(msg);
    if (lastSent === s) {{ return; }}
    lastSent = s;
    try {{
      window.parent.postMessage({{type: 'tlx_video', event_type: event_type, extra: extra||'', url: url}}, '*');
      if (window.Streamlit) {{ Streamlit.setComponentValue(msg); }}
    }} catch(e) {{}}
  }}

  function snapshot(action) {{
    var payload = JSON.stringify({{
      watched_per_segment: segWatch.slice(0),
      segment_names: segs.map(function(s){{return s.name;}}),
      segment_durs: segs.map(function(s){{return s.dur;}}),
      action: action
    }});
    send('video_segment_watch', payload);
  }}

  // Бизнес-метрики ролика: удержание первых 3 сек и досмотры 25/50/75/100%.
  function checkMilestones() {{
    var sec = v.currentTime;
    if (!flags.ret3 && sec >= 3) {{ flags.ret3 = true; send('video_retention_3s', ''); }}
    var dur = v.duration;
    if (isFinite(dur) && dur > 0) {{
      var pct = sec / dur;
      if (!flags.w25 && pct >= 0.25) {{ flags.w25 = true; send('video_watch_25', ''); }}
      if (!flags.w50 && pct >= 0.50) {{ flags.w50 = true; send('video_watch_50', ''); }}
      if (!flags.w75 && pct >= 0.75) {{ flags.w75 = true; send('video_watch_75', ''); }}
    }}
  }}

  v.addEventListener('play', function(){{
    if (!playLogged) {{ playLogged = true; send('video_play', ''); }}
  }});

  v.addEventListener('timeupdate', function(){{
    var sec = Math.floor(v.currentTime);
    if (lastSec !== sec && isFinite(sec) && sec >= 0 && sec <= MAX) {{
      lastSec = sec;
      segWatch[segIndex(sec)] += 1;
    }}
    checkMilestones();
  }});

  v.addEventListener('ended', function(){{
    if (!completeLogged) {{
      completeLogged = true;
      if (!flags.w100) {{ flags.w100 = true; send('video_watch_100', ''); }}
      snapshot('ended');
    }}
  }});

  v.addEventListener('pause', function(){{
    snapshot('pause');
  }});
}})();
</script>
"""


def _build_player_html(video_url: str, reklam_href: str, reklam_extra: str, segs: list) -> str:
    src = _esc(video_url)
    seg_json = _esc(json.dumps(segs, ensure_ascii=False))
    return _PLAYER_HTML.format(
        src=src, reklam_href=reklam_href, reklam_extra=reklam_extra, seg_json=seg_json
    )


def _log_player_event(ev: str, extra: str, video_url: str, variant: str, utm: str) -> None:
    """Событие из JS-компонента → запись в CSV-лог аналитики (по типу события)."""
    try:
        if ev == "video_play":
            analytics.log_video_play(video_url, variant=variant, utm=utm)
        elif ev == "video_completed":
            analytics.log_video_completed(video_url, variant=variant, utm=utm)
        elif ev == "video_segment_watch":
            analytics.log_event("video_segment_watch", extra=extra)
        elif ev in (
            "video_retention_3s",
            "video_watch_25",
            "video_watch_50",
            "video_watch_75",
            "video_watch_100",
        ):
            analytics.log_video_progress(ev, video_url, variant=variant, utm=utm)
        elif ev == "reklama_click":
            analytics.log_reklama_click(video_url, variant=variant, utm=utm)
    except Exception:
        pass


_STAGE_KEYS = ["preprocess", "predict", "model_load"]


def _remember_timing(data: dict):
    """Добавляет замер стадий по job_id в историю сессии (хранятся последние 12)."""
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


def _p50_p95(vals):
    arr = np.array([v for v in vals if v > 0], dtype=float)
    if arr.size == 0:
        return None, None
    return int(np.percentile(arr, 50)), int(np.percentile(arr, 95))


def _cold_warm_table() -> pd.DataFrame:
    """p50/p95 cold/warm по накопленной истории сессии."""
    hist = list(st.session_state.get("timings_history") or [])
    rows = []
    for name, cold_flag in (("Холодный", True), ("Тёплый", False)):
        vals = [h.get("latency", 0) for h in hist if bool(h.get("cold")) == cold_flag]
        p50, p95 = _p50_p95(vals)
        if p50 is None:
            continue
        rows.append({"Замер": f"{name} (n={len(vals)})", "p50, мс": p50, "p95, мс": p95})
    return pd.DataFrame(rows)


def render_stage_timings(data: dict):
    """Технический блок диагностики: хронометраж этапов генерации
    (preprocess / predict / cold-start) + p50/p95 по истории сессии.
    Бэкенд отдаёт stage_timing_ms (в b/c ключ назывался timings_ms)."""
    timings = data.get("timings_ms") or data.get("stage_timing_ms") or {}
    if not timings:
        st.caption("Хронометраж недоступен: бэкенд не вернул timings этапа.")
        return
    _remember_timing(data)

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
        table = _cold_warm_table()
        if not table.empty:
            st.dataframe(table, hide_index=True)
            st.caption(
                "Пакет замеров: последние 12 генераций сессии. "
                "Холодный — первый вызов после старта контейнера; "
                "latency измеряется на фронте (клиент → сервер)."
            )
        else:
            st.caption("Замеры накапливаются в сессии — сгенерируйте ролик ещё раз.")


def _render_video(
    video_url: str, ranked_factors: list | None = None, variant: str = "", utm: str = ""
) -> None:
    if not USE_CUSTOM_PLAYER:
        st.video(video_url)
        return

    # UTM-хелпер живёт в app.py (контракт тестов app.with_utm); импортируем
    # лениво, чтобы не зациклить app → videoapp → app.
    from app import with_utm  # noqa: PLC0415

    reklam_href = _esc(with_utm(video_url, {"utm_content": variant} if variant else None))
    reklam_extra = _esc(f"url={video_url}; variant={variant}" + (f"; {utm}" if utm else ""))

    segs = segment_table(ranked_factors)
    html = _build_player_html(video_url, reklam_href, reklam_extra, segs)
    ret = components.html(html, height=780, scrolling=False)

    # Обработка события, возвращённого компонентом с предыдущих ре-ранов.
    if isinstance(ret, dict) and ret.get("type"):
        _log_player_event(ret["type"], ret.get("extra", ""), video_url, variant, utm)

    # Fallback на случай, если JS-канал не сработал: фиксируем хотя бы показ.
    if not st.session_state.get("_video_play_logged"):
        try:
            analytics.log_video_play(video_url, variant=variant, utm=utm)
        except Exception:
            pass
        st.session_state["_video_play_logged"] = True
