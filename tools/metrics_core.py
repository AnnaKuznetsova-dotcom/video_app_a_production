"""
Общая логика: выгрузка CSV-метрик приложения в pandas и расчёт показателей
Группы Б (AI) на основе реально собранных данных.

Группа А (контроль) вводится пользователем вручную через input() — скрипт
сравнивает её с фактическими метриками Группы Б.

Данные, читаемые из CSV:
    frontend/analytics_output/sessions.csv   — визиты (client_id).
    frontend/analytics_output/events.csv     — события (preview_click,
                                               lead_submit, latency_record).
    backend/data_metrics/metrics.csv          — технические инференсы.
    backend/data_metrics/summary.csv          — сводка (latency/error/cost).

Что НЕ извлекается из CSV (требует внешних источников) — запрашивается вручную:
    - Video Completion Rate (VCR) — нужен видеоплеер с событиями.
    - Accuracy классификатора — нужна CRM-разметка реальных сделок.
    - Hit Ratio топ-3 фактора — нужны отзывы покупателей после сделки.
"""

import csv
import os
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def locate_project(root_arg: str | None = None) -> str:
    """Возвращает корень проекта (исправляет, если передана tools/ или backend/)."""
    root = os.path.abspath(root_arg or PROJECT_ROOT)
    if os.path.basename(root) in ("frontend", "backend", "tools"):
        root = os.path.dirname(root)
    return root


def read_csv(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Загрузка CSV в pandas DataFrame (как просили «загрузить в pandas»)
# ---------------------------------------------------------------------------
def load_dataframes(root: str) -> dict[str, object]:
    """Читает все CSV-файлы метрик в pandas.DataFrame.

    Возвращает {"events": df, "sessions": df, "backend": df, "summary": df}.
    Каждая df — таблица pandas; с ней можно строить графики прямо в jupyter
    или использовать в plotly. Дополнительно указаны пути, откуда прочитаны.
    """
    import pandas as pd

    paths = {
        "events": os.path.join(root, "frontend", "analytics_output", "events.csv"),
        "sessions": os.path.join(root, "frontend", "analytics_output", "sessions.csv"),
        "backend": os.path.join(root, "backend", "data_metrics", "metrics.csv"),
        "summary": os.path.join(root, "backend", "data_metrics", "summary.csv"),
    }
    out = {}
    for key, path in paths.items():
        out[key] = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    out["_paths"] = paths
    return out


def _uniq(values: list[str]) -> int:
    return len({v for v in values if v})


# ---------------------------------------------------------------------------
# Загрузка и агрегация Группы Б из CSV
# ---------------------------------------------------------------------------
def load_group_b(root: str) -> dict[str, object]:
    events = read_csv(os.path.join(root, "frontend", "analytics_output", "events.csv"))
    sessions = read_csv(os.path.join(root, "frontend", "analytics_output", "sessions.csv"))
    backend = read_csv(os.path.join(root, "backend", "data_metrics", "metrics.csv"))
    read_csv(
        os.path.join(root, "backend", "data_metrics", "summary.csv")
    )  # noqa: F841 — прогрев/валидация файла

    # --- Посетители / сессии ---
    session_ids = [r.get("client_id", "") for r in sessions]
    users = _uniq(session_ids)  # уникальные пользователи (по client_id)
    sessions_n = len(session_ids)  # общее число визитов

    # --- События ---
    clicks = [r for r in events if r.get("event_type") == "preview_click"]
    leads = [r for r in events if r.get("event_type") == "lead_submit"]
    lat_events = [r for r in events if r.get("event_type") == "latency_record"]

    ctr = (len(clicks) / users * 100) if users else 0.0
    cr = (len(leads) / users * 100) if users else 0.0

    # --- TTL (часы): первый заход -> последний лид по одному client_id ---
    ttl_hours: list[float] = []
    for cid in {r.get("client_id") for r in leads}:
        first = next((r.get("ts_iso") for r in sessions if r.get("client_id") == cid), None)
        lead_last = next(
            (
                r.get("ts_iso")
                for r in events
                if r.get("client_id") == cid and r.get("event_type") == "lead_submit"
            ),
            None,
        )
        if first and lead_last:
            try:
                t0 = datetime.fromisoformat(first)
                t1 = datetime.fromisoformat(lead_last)
                ttl_hours.append((t1 - t0).total_seconds() / 3600.0)
            except Exception:
                pass
    ttl_avg_hours = (sum(ttl_hours) / len(ttl_hours)) if ttl_hours else None

    # --- Latency (клиент->сервер) и Error Rate ---
    lats = []
    for r in lat_events:
        extra = r.get("extra", "") or ""
        if "latency_ms=" in extra:
            try:
                lats.append(int(extra.split("latency_ms=")[1].split(";")[0]))
            except Exception:
                pass
    latency_p95 = _p95(lats) if lats else None
    latency_avg = (sum(lats) / len(lats)) if lats else None

    ok_rows = [r for r in backend if r.get("success") == "1"]
    errs = [r for r in backend if r.get("success") == "0"]
    err_rate = (len(errs) / len(backend) * 100) if backend else None

    return {
        "users": users,
        "sessions": sessions_n,
        "clicks": len(clicks),
        "leads": len(leads),
        "ctr_pct": ctr,
        "cr_pct": cr,
        "ttl_hours": ttl_avg_hours,
        "latency_ms_avg": latency_avg,
        "latency_ms_p95": latency_p95,
        "error_rate_pct": err_rate,
        "inferences": len(backend),
        "inferences_ok": len(ok_rows),
        "inferences_err": len(errs),
        # сырые данные для графиков
        "_events": events,
        "_sessions": sessions,
        "_backend": backend,
    }


def _p95(vals: list[int]) -> int:
    s = sorted(vals)
    return s[int((len(s) - 1) * 0.95)]


# ---------------------------------------------------------------------------
# Ввод данных Группы А (контроль) — вручную через input()
# ---------------------------------------------------------------------------
def ask_group_a() -> dict[str, object]:
    print("\n" + "=" * 60)
    print("ВВОД ДАННЫХ ГРУППЫ А (КОНТРОЛЬ: стандартное/статичное видео)")
    print("=" * 60)
    print("Введите основные данные контрольной группы (нажмите Enter, чтобы")
    print("пропустить поле — оно не попадёт в сравнение).")

    a = {}
    a["users"] = _ask_int("Число посетителей (визитов) группы А")
    a["leads"] = _ask_int("Число лидов группы А")
    a["clicks"] = _ask_int("Число кликов «Смотреть видео» группы А")
    a["ttl_hours"] = _ask_float("Средний Time-to-Lead группы А (часы)")
    a["latency_ms_p95"] = _ask_float("Latency P95 группы А (мс)")
    a["error_rate_pct"] = _ask_float("Error Rate группы А (%)")

    print("\nДалее — метрики, которые НЕ собираются из CSV автоматически.")
    print("Введите их вручную (можно пропустить).")
    a["vcr_pct_b"] = _ask_float("VCR (Video Completion Rate) группы Б, %")
    a["vcr_pct_a"] = _ask_float("VCR группы А, %")
    a["accuracy_pct"] = _ask_float("Accuracy классификатора, %")
    a["hit_ratio_pct"] = _ask_float("Hit Ratio топ-3 факторов с отзывами, %")
    return a


def _ask_int(label: str) -> int | None:
    v = input(f"{label}: ").strip().replace(",", ".")
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _ask_float(label: str) -> float | None:
    v = input(f"{label}: ").strip().replace(",", ".")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Функции сравнения Б vs А
# ---------------------------------------------------------------------------
def pct_change(b: float | None, a: float | None) -> float | None:
    """Процентное изменение Б относительно А: (Б-А)/А*100."""
    if b is None or a is None or a == 0:
        return None
    return (b - a) / a * 100.0


def pp_diff(b: float | None, a: float | None) -> float | None:
    """Разница в процентных пунктах: Б - А."""
    if b is None or a is None:
        return None
    return b - a


def fmt_num(v: float | None, digits: int = 2, suffix: str = "") -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}{suffix}"
