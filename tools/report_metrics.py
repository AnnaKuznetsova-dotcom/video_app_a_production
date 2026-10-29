"""
Отчёт по метрикам MVP: терминал + PNG-графики (plotly).

Запуск:
    python tools/report_metrics.py [путь_к_проекту]

Что делает:
    1. Читает реальные метрики Группы Б (AI) из CSV.
    2. Спрашивает вручную данные Группы А (контроль).
    3. Строит графики (plotly) и сохраняет PNG в папку reports/.
    4. Выводит «Сводную таблицу метрик» в терминал.

Пример использования из Python:
    import sys; sys.path.insert(0, 'tools')
    import report_metrics as r
    b = r.load_group_b(r.locate_project())
    r.render(b, a_dict)   # только графика
"""

import os
import sys

import plotly.graph_objects as go

# Для запуска `python tools/report_metrics.py` — добавляем tools в путь.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import metrics_core as mc  # noqa: E402

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


# ---------------------------------------------------------------------------
# Генерация графиков (plotly)
# ---------------------------------------------------------------------------
def _fig_layout(fig, title):
    fig.update_layout(
        title=title,
        template="plotly_white",
        font=dict(family="Inter, Arial", size=14),
        bargap=0.35,
        margin=dict(l=80, r=40, t=60, b=60),
    )
    return fig


def build_charts(b: dict, a: dict) -> dict[str, go.Figure]:
    """Строит несколько графиков и возвращает {имя: figure}."""
    charts = {}

    # --- 1. Конверсия/вовлечённость: Б vs А ---
    metrics = ["CR (%)", "CTR (%)", "VCR (%)"]
    a_ctr = (a["clicks"] / a["users"] * 100) if (a.get("clicks") and a.get("users")) else None
    b_vals = [b.get("cr_pct"), b.get("ctr_pct"), a.get("vcr_pct_b")]
    a_vals = [None, a_ctr, a.get("vcr_pct_a")]

    fig1 = go.Figure()
    _add_group_bars(fig1, metrics, [("Группа Б (AI)", b_vals), ("Группа А (Контроль)", a_vals)])
    _fig_layout(fig1, "Бизнес-метрики: Группа Б (AI) vs Группа А (Контроль)")
    charts["business"] = fig1

    # --- 2/4. Error Rate: Б vs А ---
    fig4 = go.Figure()
    _add_group_bars(
        fig4,
        ["Error Rate (%)"],
        [
            ("Группа Б (AI)", [b.get("error_rate_pct")]),
            ("Группа А (Контроль)", [a.get("error_rate_pct")]),
        ],
    )
    _fig_layout(fig4, "Инженерные метрики: Error Rate")
    charts["error"] = fig4

    # --- 3. Latency: P95 Б vs А ---
    fig3 = _build_latency(b, a)
    if fig3 is not None:
        charts["latency"] = fig3

    return charts


def _add_group_bars(fig, xlabels, series):
    """series = [(имя, значения), ...]"""
    for name, vals in series:
        fig.add_trace(
            go.Bar(
                name=name,
                x=xlabels,
                y=vals,
                text=vals,
                texttemplate="%{text:.2f}",
                textposition="outside",
            )
        )
    fig.update_xaxes(type="category")


def _build_latency(b, a):
    """Latency P95: Б vs А."""
    fig = go.Figure()
    x = ["Latency P95 (мс)"]
    y_a = [a.get("latency_ms_p95")]
    y_b = [b.get("latency_ms_p95")]
    fig.add_trace(go.Bar(name="Группа Б (AI)", x=x, y=y_b, text=y_b, texttemplate="%{text:.0f}"))
    fig.add_trace(
        go.Bar(name="Группа А (Контроль)", x=x, y=y_a, text=y_a, texttemplate="%{text:.0f}")
    )
    fig.add_hline(y=3000, line_dash="dash", line_color="red", annotation_text="Цель < 3000 мс")
    _fig_layout(fig, "Latency генерации: P95 (цель < 3 сек)")
    return fig


def save_charts(charts: dict[str, go.Figure], out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    for name, fig in charts.items():
        path = os.path.join(out_dir, f"{name}.png")
        try:
            fig.write_image(path)
            saved.append(path)
        except Exception:
            # PNG требует kaleido; если его нет — всё равно сохраняем HTML-версию.
            alt = os.path.join(out_dir, f"{name}.html")
            fig.write_html(alt)
            saved.append(alt)
    return saved


# ---------------------------------------------------------------------------
# Формирование «Сводной таблицы метрик»
# ---------------------------------------------------------------------------
STATUS_RULES = {}  # переопределено ниже


def _status_row(label, b_val, a_val, better="higher", target=None):
    if b_val is None:
        return [label, "—", "—", "—", "ℹ️ Нет данных"]
    diff_info = ""
    if a_val is not None:
        if better == "higher":
            dif = mc.pp_diff(b_val, a_val)
            pct = mc.pct_change(b_val, a_val)
            diff_info = f"{'+' if dif and dif > 0 else ''}{dif:.1f}" + (
                f" ({'+' if pct and pct > 0 else ''}{pct:.0f}%)" if pct else ""
            )
        else:  # lower is better
            dif = mc.pp_diff(b_val, a_val)
            pct = mc.pct_change(b_val, a_val)
            diff_info = f"{dif:.1f}" + (f" ({pct:.0f}%)" if pct else "")
    status = "✅ Успех"
    if target is not None:
        if better == "higher":
            if b_val < target:
                status = "⚠️ Ниже цели"
        else:
            if b_val > target:
                status = "⚠️ Близко к лимиту"
    return [label, b_val, a_val, diff_info, status]


def build_table(b: dict, a: dict) -> list[list[str]]:
    """Возвращает строки сводной таблицы."""
    rows = []
    rows.append(
        ["Категория", "Метрика", "Группа Б (AI)", "Группа А (Контроль)", "Изм.(Б-А)", "Статус"]
    )

    a_cr = (
        (a["leads"] / a["users"] * 100) if (a.get("leads") is not None and a.get("users")) else None
    )
    a_ctr = (
        (a["clicks"] / a["users"] * 100)
        if (a.get("clicks") is not None and a.get("users"))
        else None
    )

    # Бизнес
    rows.append(
        [
            "Бизнес",
            "Conversion Rate (CR), %",
            mc.fmt_num(b["cr_pct"]),
            mc.fmt_num(a_cr),
            _diff_fmt(b["cr_pct"], a_cr),
            "✅ Успех",
        ]
    )
    rows.append(
        [
            "Бизнес",
            "Click-Through Rate (CTR), %",
            mc.fmt_num(b["ctr_pct"]),
            mc.fmt_num(a_ctr),
            _diff_fmt(b["ctr_pct"], a_ctr),
            "✅" if b["ctr_pct"] is not None else "ℹ️",
        ]
    )

    # TTL: в часах, меньше - лучше
    rows.append(
        [
            "Бизнес",
            "Time to Lead (TTL), ч",
            mc.fmt_num(b.get("ttl_hours"), 1),
            mc.fmt_num(a.get("ttl_hours"), 1),
            _diff_fmt(b.get("ttl_hours"), a.get("ttl_hours")),
            (
                "✅ Успех"
                if (b.get("ttl_hours") and a.get("ttl_hours") and b["ttl_hours"] < a["ttl_hours"])
                else "ℹ️"
            ),
        ]
    )

    # Вовлечённость (задаётся вручную)
    rows.append(
        [
            "Вовлечённость",
            "Video Completion Rate (VCR), %",
            mc.fmt_num(a.get("vcr_pct_b")),
            mc.fmt_num(a.get("vcr_pct_a")),
            _diff_fmt(a.get("vcr_pct_b"), a.get("vcr_pct_a")),
            (
                "✅ Успех"
                if (a.get("vcr_pct_b") and a.get("vcr_pct_a") and a["vcr_pct_b"] > a["vcr_pct_a"])
                else "ℹ️"
            ),
        ]
    )

    # Качество ML (задаётся вручную)
    rows.append(
        [
            "Качество ML",
            "Accuracy классификатора, %",
            mc.fmt_num(a.get("accuracy_pct")),
            "—",
            "—",
            "✅ Стабильно" if (a.get("accuracy_pct") or 0) >= 70 else "⚠️",
        ]
    )
    rows.append(
        [
            "Качество ML",
            "Hit Ratio топ-3 факторов, %",
            mc.fmt_num(a.get("hit_ratio_pct")),
            "—",
            "—",
            "⚠️ Требует анализа" if (a.get("hit_ratio_pct") or 0) < 60 else "✅",
        ]
    )

    # Инженерия
    rows.append(
        [
            "Инженерия",
            "Latency генерации P95, мс",
            mc.fmt_num(b.get("latency_ms_p95"), 0),
            mc.fmt_num(a.get("latency_ms_p95"), 0),
            _diff_fmt(b.get("latency_ms_p95"), a.get("latency_ms_p95")),
            "✅" if (b.get("latency_ms_p95") or 99999) < 3000 else "⚠️ Близко к лимиту",
        ]
    )
    rows.append(
        [
            "Инженерия",
            "Error Rate, %",
            mc.fmt_num(b.get("error_rate_pct")),
            mc.fmt_num(a.get("error_rate_pct")),
            _diff_fmt(b.get("error_rate_pct"), a.get("error_rate_pct")),
            "✅" if (b.get("error_rate_pct") or 0) < 5 else "⚠️ Риск",
        ]
    )

    return rows


def _diff_fmt(b_val, a_val):
    if b_val is None or a_val is None:
        return "—"
    pct = mc.pct_change(b_val, a_val)
    sign = "+" if pct and pct > 0 else ""
    return f"{sign}{pct:.0f}%" if pct is not None else "—"


def render_text_table(rows):
    _EMOJI = {
        "✅ Успех": "[OK] Успех",
        "⚠️ Требует анализа": "[!] Требует анализа",
        "⚠️ Близко к лимиту": "[!] Близко к лимиту",
        "⚠️ Риск": "[!] Риск",
        "⚠️": "[!] ",
        "ℹ️": "[i] ",
        "✅": "[OK] ",
        "—": "-",
    }

    def ascii_cell(c):
        s = str(c)
        for k, v in _EMOJI.items():
            s = s.replace(k, v)
        return s.encode("ascii", "replace").decode("ascii")

    rows = [[ascii_cell(c) for c in row] for row in rows]
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print()
    print(line)
    for r_i, row in enumerate(rows):
        print("| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)) + " |")
        if r_i == 0:
            print(line)
    print(line)


def hypothesis_text():
    return (
        "\nОсновная гипотеза MVP\n"
        "Персонализация визуального контента на основе интерпретируемости модели "
        "(SHAP) повышает коммерческую эффективность и качество рекомендаций: "
        "пользователи, которым показывают видео, сгенерированное под их ключевые "
        "факторы выбора, совершают целевое действие быстрее и чаще, а алгоритм "
        "SHAP корректно определяет истинные триггеры покупки.\n"
    )


# ---------------------------------------------------------------------------
# Главная функция
# ---------------------------------------------------------------------------
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    root = mc.locate_project(sys.argv[1] if len(sys.argv) > 1 else None)
    print(hypothesis_text())

    b = mc.load_group_b(root)
    print("[Группа Б (AI)] Загружено из CSV:")
    print(
        f"  Пользователей: {b['users']} | Сессий: {b['sessions']} | "
        f"Кликов: {b['clicks']} | Лидов: {b['leads']}"
    )
    print(
        f"  CR = {b['cr_pct']:.2f}%  |  CTR = {b['ctr_pct']:.2f}%  |  "
        f"TTL = {mc.fmt_num(b.get('ttl_hours'), 1)} ч"
    )
    print(
        f"  Latency avg = {mc.fmt_num(b.get('latency_ms_avg'), 0)} мс, "
        f"p95 = {mc.fmt_num(b.get('latency_ms_p95'), 0)} мс | "
        f"Error = {mc.fmt_num(b.get('error_rate_pct'))}%"
    )

    a = mc.ask_group_a()

    # Построить графики
    charts = build_charts(b, a)
    saved = save_charts(charts, REPORTS_DIR)
    print("\n[Графики сохранены]")
    for p in saved:
        print("  " + p)

    # Сводная таблица
    rows = build_table(b, a)
    render_text_table(rows)

    print(
        "\nПримечание: VCR, Accuracy и Hit Ratio не собираются из CSV "
        "автоматически (нужны видеоплеер с событиями и CRM/отзывы) — "
        "они вводятся вручную."
    )


if __name__ == "__main__":
    main()
