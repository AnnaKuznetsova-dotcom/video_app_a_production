"""
Простой отчёт по метрикам — читает CSV-файлы и печатает удобную сводку.
Никакого SQL не нужно.

Запуск:
    python tools/view_metrics.py [путь_к_папке_проекта]

По умолчанию ищет папки проекта относительно этого файла.
"""

import csv
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BACKEND_CSV = os.path.join(PROJECT_ROOT, "backend", "data_metrics", "metrics.csv")
BACKEND_SUMMARY = os.path.join(PROJECT_ROOT, "backend", "data_metrics", "summary.csv")
FRONTEND_EVENTS = os.path.join(PROJECT_ROOT, "frontend", "analytics_output", "events.csv")
FRONTEND_SESSIONS = os.path.join(PROJECT_ROOT, "frontend", "analytics_output", "sessions.csv")


# История формата metrics.csv (важно: заголовок на диске может быть СТАРЫМ при
# новых строках — определяем схему ПО ЧИСЛУ ПОЛЕЙ в строке, как
# backend/pipeline/metrics_tracker.py):
#   легаси 11 колонок: [.., total_ms, success, error]
#   легаси 12/13/19:   + (удалённые колонки SHAP-интерпретируемости)
#   v5 (15 колонок):   [ts_iso..total_ms, success, error, variant,
#                       preprocess_ms, predict_ms, model_load_ms, is_cold]
_ROW_BASE_V5 = [
    "ts_iso",
    "endpoint",
    "settlement",
    "klass",
    "fragments_used",
    "download_ms",
    "render_ms",
    "total_ms",
]
_ROW_BASE_LEGACY = [
    "ts_iso",
    "endpoint",
    "settlement",
    "klass",
    "top_factors",
    "fragments_used",
    "download_ms",
    "render_ms",
    "total_ms",
]


def _map_csv_row(ln):
    n = len(ln)
    if n == 15:  # v5: актуальная схема
        d = dict(zip(_ROW_BASE_V5, ln[:8], strict=False))
        d["success"] = ln[8]
        d["error"] = ln[9]
        d["variant"] = ln[10]
        d["preprocess_ms"] = ln[11]
        d["predict_ms"] = ln[12]
        d["model_load_ms"] = ln[13]
        d["is_cold"] = ln[14]
        return d
    # легаси (v1..v4)
    d = dict(zip(_ROW_BASE_LEGACY, ln[:9], strict=False))
    if n >= 12:
        d["success"] = ln[10]
        d["error"] = ln[11]
    else:
        d["success"] = ln[9] if n >= 10 else ""
        d["error"] = ln[10] if n >= 11 else ""
    if n >= 19:
        d["variant"] = ln[13]
        d["preprocess_ms"] = ln[14]
        d["predict_ms"] = ln[15]
        d["model_load_ms"] = ln[17]
        d["is_cold"] = ln[18]
    else:
        d["variant"] = ""
        d["preprocess_ms"] = ""
        d["predict_ms"] = ""
        d["model_load_ms"] = ""
        d["is_cold"] = ""
    return d


def _read_rows(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # заголовок не учитываем — схему даёт _map_csv_row
        for ln in reader:
            if not ln or (len(ln) == 1 and not ln[0].strip()):
                continue
            rows.append(_map_csv_row(ln))
    return rows


def _avg_ms(ok, field):
    vals = [int(r[field]) for r in ok if (r.get(field) or "").isdigit()]
    return sum(vals) // len(vals) if vals else None


def _pct_ms(ok, field, p):
    vals = sorted(int(r[field]) for r in ok if (r.get(field) or "").isdigit())
    if not vals:
        return None
    return vals[int((len(vals) - 1) * p)]


def _print_latency_stats(ok):
    print(
        f"  Latency:   avg={_avg_ms(ok, 'total_ms')}ms  p50={_pct_ms(ok, 'total_ms', 0.5)}ms  p95={_pct_ms(ok, 'total_ms', 0.95)}ms"
    )
    print(f"  Render:    avg={_avg_ms(ok, 'render_ms')}ms  p95={_pct_ms(ok, 'render_ms', 0.95)}ms")
    print(f"  Download:  avg={_avg_ms(ok, 'download_ms')}ms")


def _print_backend_inferences():
    rows = _read_rows(BACKEND_CSV)
    if not rows:
        print("  Нет данных в", BACKEND_CSV)
        return
    ok = [r for r in rows if r.get("success") == "1"]
    errs = [r for r in rows if r.get("success") == "0"]
    total = len(rows)
    print(f"  Всего инференсов: {total} | Успешно: {len(ok)} | Ошибки: {len(errs)}")
    print(f"  Error Rate: {100.0*len(errs)/total:.2f}%" if total else "  n/a")
    _print_latency_stats(ok)


def _print_summary_metrics():
    """Сводка из summary.csv (метрики с внешними источниками помечены NA)."""
    summary_rows = _read_rows(BACKEND_SUMMARY)
    smap = {
        r.get("metric"): r for r in summary_rows if r.get("metric") and r.get("metric") != "metric"
    }
    if not smap:
        return
    print("\n  СВОДКА (flag | значение | описание | формула):")
    print("  " + " | ".join(["метрика", "значение", "описание", "формула"]))
    for k, r in smap.items():
        val = r.get("value", "")
        desc = r.get("description", "")
        formula = r.get("formula", "")
        print(f"  {k} | {val} | {desc} | {formula}")
    acc = smap.get("accuracy_classifier")
    if acc:
        print(
            f"  Accuracy классификатора: {acc.get('value', 'NA')}  (заполнить из размеченного тест-сета)"
        )


def _print_leads_table(leads):
    print("\n  ТАБЛИЦА ЛИДОВ (имя / телефон хранятся только в событиях frontend):")
    print("  " + " | ".join(["client_id", "время", "имя", "телефон"]))
    print("  " + "-" * 130)
    for e in sorted(leads, key=lambda x: x.get("ts_iso", ""), reverse=True):
        cid = e.get("client_id", "")
        ts = e.get("ts_iso", "")
        extra = e.get("extra", "") or ""
        name = phone = ""
        for part in extra.split(";"):
            part = part.strip()
            if part.startswith("name="):
                name = part[len("name=") :]
            elif part.startswith("phone="):
                phone = part[len("phone=") :]
        print(f"  {cid} | {ts} | {name} | {phone}")


def _print_frontend_business():
    events = _read_rows(FRONTEND_EVENTS)
    sessions = _read_rows(FRONTEND_SESSIONS)
    sessions_cnt = len(sessions)
    samples = [e for e in events if e.get("event_type") == "preview_click"]
    leads = [e for e in events if e.get("event_type") == "lead_submit"]

    print(f"  Визитов (сессий): {sessions_cnt}")
    if not sessions_cnt:
        return
    ctr = 100.0 * len(samples) / sessions_cnt
    cr = 100.0 * len(leads) / sessions_cnt
    print(f"  Кликов «Смотреть видео»: {len(samples)}  ->  CTR = {ctr:.2f}%")
    print(f"  Лидов «Заказать звонок»:  {len(leads)}  ->  CR  = {cr:.2f}%")
    empties = [e for e in events if e.get("event_type") == "lead_submit_empty"]
    print(f"  Лидов (пустая форма): {len(empties)}")
    if leads:
        _print_leads_table(leads)

    # VCR: досмотры ролика до конца.
    plays = [e for e in events if e.get("event_type") == "video_play"]
    completed = [e for e in events if e.get("event_type") == "video_completed"]
    if plays:
        print(
            f"  Просмотров ролика: {len(plays)} | Досмотров до конца: {len(completed)}  "
            f"->  VCR = {100.0*len(completed)/len(plays):.2f}%"
        )
    else:
        print("  VCR: нет данных (нужны события video_play / video_completed)")

    # Time-to-Lead: среднее время от первого захода до лида по одному client_id.
    _print_ttl(events, sessions, leads)
    # Latency из frontend-событий.
    _print_frontend_latency(events)


def _print_ttl(events, sessions, leads):
    lead_cids = set(e.get("client_id") for e in leads)
    ttl_seconds = []
    for cid in lead_cids:
        first = next((s.get("ts_iso") for s in sessions if s.get("client_id") == cid), None)
        lead_last = next(
            (
                e.get("ts_iso")
                for e in events
                if e.get("client_id") == cid and e.get("event_type") == "lead_submit"
            ),
            None,
        )
        if first and lead_last:
            try:
                t0 = datetime.fromisoformat(first)
                t1 = datetime.fromisoformat(lead_last)
                ttl_seconds.append((t1 - t0).total_seconds())
            except Exception:
                pass
    if ttl_seconds:
        avg_ttl = sum(ttl_seconds) / len(ttl_seconds)
        hh = int(avg_ttl // 3600)
        mm = int((avg_ttl % 3600) // 60)
        print(f"  Средний Time-to-Lead: {hh} ч {mm} мин")
    else:
        print("  Time-to-Lead: нет данных (нужны и сессия, и лид одного клиента)")


def _print_frontend_latency(events):
    lat = []
    for e in events:
        if e.get("event_type") != "latency_record":
            continue
        extra = e.get("extra") or ""
        if "latency_ms=" in extra:
            try:
                lat.append(int(extra.split("latency_ms=")[1].split(";")[0]))
            except Exception:
                continue
    if lat:
        p95 = sorted(lat)[int((len(lat) - 1) * 0.95)]
        print(f"  Latency (клиент->сервер, из фронта): avg={sum(lat)//len(lat)}ms  p95={p95}ms")


def main():
    load_if_main(sys.argv[1] if len(sys.argv) > 1 else None)

    print("=" * 62)
    print("ОТЧЁТ ПО МЕТРИКАМ ПРИЛОЖЕНИЯ")
    print("=" * 62)

    print("\n[1] ТЕХНИЧЕСКИЕ МЕТРИКИ (backend)")
    _print_backend_inferences()
    _print_summary_metrics()

    print("\n[2] БИЗНЕС-МЕТРИКИ (frontend)")
    _print_frontend_business()

    print("\n[3] ГДЕ ЛЕЖАТ ФАЙЛЫ:")
    print("  backend :", BACKEND_CSV)
    print("  backend :", BACKEND_SUMMARY)
    print("  frontend:", FRONTEND_EVENTS)
    print("  frontend:", FRONTEND_SESSIONS)
    print("\nМетрики также доступны по адресу:  {BACKEND_URL}/metrics  (JSON)")


def load_if_main(path_arg=None):
    global BACKEND_CSV, BACKEND_SUMMARY, FRONTEND_EVENTS, FRONTEND_SESSIONS
    base = path_arg if path_arg else PROJECT_ROOT
    root = os.path.abspath(base)
    if os.path.basename(root) == "frontend":
        root = os.path.dirname(root)
    BACKEND_CSV = os.path.join(root, "backend", "data_metrics", "metrics.csv")
    BACKEND_SUMMARY = os.path.join(root, "backend", "data_metrics", "summary.csv")
    FRONTEND_EVENTS = os.path.join(root, "frontend", "analytics_output", "events.csv")
    FRONTEND_SESSIONS = os.path.join(root, "frontend", "analytics_output", "sessions.csv")


if __name__ == "__main__":
    main()
