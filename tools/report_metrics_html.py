"""
HTML-отчёт по метрикам MVP (самодостаточная страница с графиками plotly).

Запуск:
    python tools/report_metrics_html.py [путь_к_проекту]

Откроет интерактивный отчёт в браузере и сохранит копию в reports/report.html.
Содержит: гипотезу, сводную таблицу, интерактивные графики.
"""

import html
import os
import sys
import webbrowser

import plotly.graph_objects as go

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import metrics_core as mc  # noqa: E402
import report_metrics as rm  # noqa: E402   (переиспользуем build_charts/build_table)

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
HTML_PATH = os.path.join(REPORTS_DIR, "report.html")


def _chart_html(fig: go.Figure, height: int = 420) -> str:
    fig.update_layout(height=height, template="plotly_white", title_font=dict(size=16))
    return fig.to_html(full_html=False, include_plotlyjs=False, default_height=f"{height}px")


def build_html(b: dict, a: dict) -> str:
    charts = rm.build_charts(b, a)
    table_rows = rm.build_table(b, a)

    # headline numbers
    def card(label, value, note=""):
        return (
            f'<div class="card"><div class="label">{label}</div>'
            f'<div class="value">{value}</div><div class="note">{note}</div></div>'
        )

    cr = f"{b['cr_pct']:.2f}%" if b.get("cr_pct") is not None else "—"
    ctr = f"{b['ctr_pct']:.2f}%" if b.get("ctr_pct") is not None else "—"
    leads = b.get("leads", 0)
    users = b.get("users", 0)
    ttl = mc.fmt_num(b.get("ttl_hours"), 1) + " ч" if b.get("ttl_hours") is not None else "—"
    lat = (
        mc.fmt_num(b.get("latency_ms_p95"), 0) + " мс"
        if b.get("latency_ms_p95") is not None
        else "—"
    )

    # таблица
    thead = "".join(f"<th>{html.escape(c)}</th>" for c in table_rows[0])
    tbody = ""
    for row in table_rows[1:]:
        cells = "".join(f"<td>{html.escape(str(c))}</td>" for c in row)
        tbody += "<tr>" + cells + "</tr>"

    chart_blocks = "".join(
        f"<h3>{_chart_title(name)}</h3>{_chart_html(fig)}" for name, fig in charts.items()
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Метрики MVP · Персонализированное видео</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body {{ font-family: 'Inter','Segoe UI',Arial,sans-serif; margin:0;
         background:#f6f4ef; color:#231f1a; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:28px 22px 60px; }}
  h1 {{ font-size:26px; margin:0 0 6px; color:#1c1916; }}
  h2 {{ font-size:20px; margin:34px 0 12px; color:#6b5734; }}
  h3 {{ font-size:16px; color:#444; margin:26px 0 6px; }}
  .sub {{ color:#7d7261; margin-bottom:26px; }}
  .hypothesis {{ background:#fff; border:1px solid #e4dcc8; border-left:5px solid
                 #b99b6b; border-radius:8px; padding:16px 18px; line-height:1.6; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
           gap:14px; margin:22px 0; }}
  .card {{ background:#fff; border:1px solid #e4dcc8; border-radius:10px;
          padding:14px 16px; }}
  .card .label {{ font-size:11px; letter-spacing:1px; color:#8d8273;
                 text-transform:uppercase; }}
  .card .value {{ font-size:26px; font-weight:700; color:#1c1916; margin-top:4px; }}
  .card .note {{ font-size:12px; color:#7d7261; margin-top:4px; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; margin-top:10px; }}
  th, td {{ border:1px solid #e4dcc8; padding:9px 12px; text-align:left;
           font-size:13px; }}
  th {{ background:#f1ebdd; color:#5b4a28; }}
  tr:nth-child(even) td {{ background:#faf8f2; }}
  .footnote {{ margin-top:26px; color:#8d8273; font-size:12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Отчёт по метрикам MVP</h1>
  <div class="sub">Персонализированное видео на основе SHAP · Группа Б (AI) vs Группа А (Контроль)</div>

  <div class="hypothesis"><b>Основная гипотеза MVP.</b> Персонализация визуального
    контента на основе интерпретируемости модели (SHAP) повышает коммерческую
    эффективность и качество рекомендаций: пользователи, которым показывают видео,
    сгенерированное под их ключевые факторы выбора, совершают целевое действие
    быстрее и чаще, а алгоритм SHAP корректно определяет истинные триггеры покупки.</div>

  <h2>Ключевые показатели (Группа Б, AI)</h2>
  <div class="cards">
    {card("Конверсия (CR)", cr, f"{leads} лидов / {users} пользователей")}
    {card("CTR превью", ctr, f"{b.get('clicks',0)} кликов")}
    {card("Time to Lead", ttl, "от первого захода до лида")}
    {card("Latency P95", lat, "цель &lt; 3000 мс")}
  </div>

  <h2>Сводная таблица метрик</h2>
  <table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>

  <h2>Графики</h2>
  {chart_blocks}

  <div class="footnote">VCR, Accuracy и Hit Ratio не собираются из CSV автоматически
    (нужны видеоплеер с событиями и CRM/отзывы) — они вводятся вручную при запуске
    скрипта. Файл отчёта: <b>reports/report.html</b>.</div>
</div>
</body>
</html>"""


def _chart_title(name: str) -> str:
    return {
        "business": "Бизнес-метрики: Б (AI) vs А (Контроль)",
        "latency": "Latency P95 (цель < 3 с)",
        "error": "Error Rate",
    }.get(name, name)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    root = mc.locate_project(sys.argv[1] if len(sys.argv) > 1 else None)
    b = mc.load_group_b(root)
    print("[Группа Б (AI)] из CSV:")
    print(
        f"  CR={b['cr_pct']:.2f}% CTR={b['ctr_pct']:.2f}% "
        f"TTL={mc.fmt_num(b.get('ttl_hours'),1)} ч "
        f"Latency p95={mc.fmt_num(b.get('latency_ms_p95'),0)} мс "
        f"Error={mc.fmt_num(b.get('error_rate_pct'))}%"
    )

    a = mc.ask_group_a()

    os.makedirs(REPORTS_DIR, exist_ok=True)
    page = build_html(b, a)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"\nОтчёт сохранён: {HTML_PATH}")
    print("Открываю в браузере...")
    webbrowser.open("file://" + os.path.abspath(HTML_PATH).replace("\\", "/"))


if __name__ == "__main__":
    main()
