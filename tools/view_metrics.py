"""
Простой отчёт по метрикам — читает CSV-файлы и печатает удобную сводку.
Никакого SQL не нужно.

Запуск:
    python tools/view_metrics.py [путь_к_папке_проекта]

По умолчанию ищет папки проекта относительно этого файла.
"""

import csv
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BACKEND_CSV = os.path.join(PROJECT_ROOT, "backend", "data_metrics", "metrics.csv")
BACKEND_SUMMARY = os.path.join(PROJECT_ROOT, "backend", "data_metrics", "summary.csv")
FRONTEND_EVENTS = os.path.join(PROJECT_ROOT, "frontend", "analytics_output", "events.csv")
FRONTEND_SESSIONS = os.path.join(PROJECT_ROOT, "frontend", "analytics_output", "sessions.csv")


# История формата metrics.csv (важно: заголовок на диске может быть СТАРЫМ при
# новых строках — определяем схему ПО ЧИСЛУ ПОЛЕЙ в строке, как backend/metrics.py):
#   11 колонок: [.., total_ms, success, error]
#   12 колонок: [.., total_ms, shap_mismatch_groups, success, error]
#   13 колонок: [.., total_ms, shap_mismatch_groups, success, error, groups_unique]
_ROW_BASE = [
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
    d = dict(zip(_ROW_BASE, ln[:9], strict=False))
    n = len(ln)
    if n >= 12:
        d["shap_mismatch_groups"] = ln[9]
        d["success"] = ln[10]
        d["error"] = ln[11]
        d["groups_unique"] = ln[12] if n >= 13 else ""
    else:
        d["shap_mismatch_groups"] = ""
        d["success"] = ln[9] if n >= 10 else ""
        d["error"] = ln[10] if n >= 11 else ""
        d["groups_unique"] = ""
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


def compute_spearman(rows):
    """Вычисляет Spearman ρ между порядком фрагментов (SHAP-важность) и
    временем просмотра каждого фрагмента, по событиям video_segment_watch.
    Порядок сегментов = порядок ranked_factors (по убыванию |SHAP|); 'общий вид'
    исключается (он не про SHAP-фактор). Усредняем ρ по всем собранным роликам.
    """
    rho_values = []
    for e in rows:
        if e.get("event_type") != "video_segment_watch":
            continue
        extra = e.get("extra") or ""
        try:
            d = json.loads(extra)
        except Exception:
            continue
        names = d.get("segment_names") or []
        watch = d.get("watched_per_segment") or []
        if not names or not watch or len(names) != len(watch):
            continue
        # Отбрасываем 'общий вид' — это не SHAP-фактор.
        idx = [i for i, n in enumerate(names) if str(n).strip().lower() != "общий вид"]
        if len(idx) < 2:
            continue
        # Ранги по порядку сегментов (SHAP-важность): 0 = самый важный.
        shap_rank = list(range(len(idx)))
        # Ранги по времени просмотра (больше времени = важнее для зрителя).
        watch_vals = [watch[i] for i in idx]
        order = sorted(range(len(watch_vals)), key=lambda i: watch_vals[i], reverse=True)
        watch_rank = [0] * len(watch_vals)
        for r, oi in enumerate(order):
            watch_rank[oi] = r
        # Spearman = корреляция Пирсона на рангах.
        n = len(shap_rank)
        mx = sum(shap_rank) / n
        my = sum(watch_rank) / n
        num = sum((a - mx) * (b - my) for a, b in zip(shap_rank, watch_rank, strict=False))
        den = (
            sum((a - mx) ** 2 for a in shap_rank) * sum((b - my) ** 2 for b in watch_rank)
        ) ** 0.5
        if den == 0:
            continue
        rho_values.append(num / den)
    if not rho_values:
        return None
    return round(sum(rho_values) / len(rho_values), 4), len(rho_values)


def load_if_main(path_arg=None):
    global BACKEND_CSV, BACKEND_SUMMARY, FRONTEND_EVENTS, FRONTEND_SESSIONS
    if path_arg:
        base = path_arg
    else:
        base = PROJECT_ROOT
    root = os.path.abspath(base)
    if os.path.basename(root) == "frontend":
        root = os.path.dirname(root)
    BACKEND_CSV = os.path.join(root, "backend", "data_metrics", "metrics.csv")
    BACKEND_SUMMARY = os.path.join(root, "backend", "data_metrics", "summary.csv")
    FRONTEND_EVENTS = os.path.join(root, "frontend", "analytics_output", "events.csv")
    FRONTEND_SESSIONS = os.path.join(root, "frontend", "analytics_output", "sessions.csv")


def main():
    load_if_main(sys.argv[1] if len(sys.argv) > 1 else None)

    print("=" * 62)
    print("ОТЧЁТ ПО МЕТРИКАМ ПРИЛОЖЕНИЯ")
    print("=" * 62)

    # ------------ Backend (технические) ------------
    print("\n[1] ТЕХНИЧЕСКИЕ МЕТРИКИ (backend)")
    rows = _read_rows(BACKEND_CSV)
    if not rows:
        print("  Нет данных в", BACKEND_CSV)
    else:
        ok = [r for r in rows if r.get("success") == "1"]
        errs = [r for r in rows if r.get("success") == "0"]
        total = len(rows)
        print(f"  Всего инференсов: {total} | Успешно: {len(ok)} | Ошибки: {len(errs)}")
        print(f"  Error Rate: {100.0*len(errs)/total:.2f}%" if total else "  n/a")

        def avg(field):
            vals = [int(r[field]) for r in ok if (r.get(field) or "").isdigit()]
            return sum(vals) // len(vals) if vals else None

        def pct(field, p):
            vals = sorted(int(r[field]) for r in ok if (r.get(field) or "").isdigit())
            if not vals:
                return None
            return vals[int((len(vals) - 1) * p)]

        print(
            f"  Latency:   avg={avg('total_ms')}ms  p50={pct('total_ms',0.5)}ms  p95={pct('total_ms',0.95)}ms"
        )
        print(f"  Render:    avg={avg('render_ms')}ms  p95={pct('render_ms',0.95)}ms")
        print(f"  Download:  avg={avg('download_ms')}ms")

        # DS-метрики качества интерпретации (заполнены backend-сводкой).
        summary_rows = _read_rows(BACKEND_SUMMARY)
        smap = {
            r.get("metric"): r
            for r in summary_rows
            if r.get("metric") and r.get("metric") != "metric"
        }
        if smap:
            print("\n  СВОДКА (flag | значение | описание | формула):")
            print("  " + " | ".join(["метрика", "значение", "описание", "формула"]))
            for k, r in smap.items():
                val = r.get("value", "")
                desc = r.get("description", "")
                formula = r.get("formula", "")
                print(f"  {k} | {val} | {desc} | {formula}")
            print()
            dfp = (
                smap.get("dominant_feature_precision_dfp", {}).get("value")
                if smap.get("dominant_feature_precision_dfp")
                else None
            )
            hc = (
                smap.get("share_high_confidence_predictions", {}).get("value")
                if smap.get("share_high_confidence_predictions")
                else None
            )
            if dfp is not None:
                print(f"  DFP (доминирование целевого фактора): {dfp}")
            if hc is not None:
                print(f"  Share of High-Confidence: {hc}")
            print(
                f"  Accuracy классификатора: {smap.get('accuracy_classifier',{}).get('value','NA') if smap.get('accuracy_classifier') else 'NA'}  "
                f"(заполнить из размеченного тест-сета)"
            )
            hr = smap.get("hit_ratio_top3_factors")
            if hr:
                print(f"  Hit Ratio Top-3: {hr.get('value')}")
            gu = smap.get("groups_unique_rate")
            if gu:
                print(
                    f"  Уникальность групп в ролике (1 клип на группу): {gu.get('value')}  "
                    f"(дублей зафиксировано: {smap.get('groups_duplicate_inferences',{}).get('value','NA') if smap.get('groups_duplicate_inferences') else 'NA'})"
                )
            sp = smap.get("spearman_rho_shap_vs_watchtime")
            if sp:
                print(f"  Spearman ρ (SHAP-порядок vs время просмотра): {sp.get('value')}")
            qar = smap.get("video_quality_pass_rate_qar")
            if qar:
                print(
                    f"  QAR (качество роликов): {qar.get('value')}  "
                    f"(вписать фактическое значение из ручной проверки)"
                )

    # ------------ Frontend (бизнес) ------------
    print("\n[2] БИЗНЕС-МЕТРИКИ (frontend)")
    sessions = _read_rows(FRONTEND_SESSIONS)
    events = _read_rows(FRONTEND_EVENTS)
    sessions_cnt = len(sessions)
    samples = [e for e in events if e.get("event_type") == "preview_click"]
    leads = [e for e in events if e.get("event_type") == "lead_submit"]

    print(f"  Визитов (сессий): {sessions_cnt}")
    if sessions_cnt:
        ctr = 100.0 * len(samples) / sessions_cnt
        cr = 100.0 * len(leads) / sessions_cnt
        print(f"  Кликов «Смотреть видео»: {len(samples)}  ->  CTR = {ctr:.2f}%")
        print(f"  Лидов «Заказать звонок»:  {len(leads)}  ->  CR  = {cr:.2f}%")
        print(
            f"  Лидов (пустая форма): {len([e for e in events if e.get('event_type') == 'lead_submit_empty'])}"
        )

        # ------------ Таблица лидов (client_id, имя, телефон, время) ------------
        if leads:
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

    # Spearman rho по посегментной телеметрии плеера.
    sp = compute_spearman(events)
    if sp:
        rho, cnt = sp
        print(f"  Spearman ρ (SHAP-порядок vs время просмотра): {rho}  (по {cnt} роликам)")
    else:
        print("  Spearman ρ: нет данных (нужны события video_segment_watch)")

        # Time-to-Lead: среднее время от первого захода до лида по одному client_id
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
                    from datetime import datetime

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

    # ------------ Latency из frontend-событий ------------
    lat = [
        int(e["extra"].split("latency_ms=")[1].split(";")[0])
        for e in events
        if e.get("event_type") == "latency_record" and "latency_ms=" in (e.get("extra") or "")
    ]
    if lat:
        print(
            f"  Latency (клиент->сервер, из фронта): avg={sum(lat)//len(lat)}ms  p95={sorted(lat)[int((len(lat)-1)*0.95)]}ms"
        )

    # ------------ Пути к файлам ------------
    print("\n[3] ГДЕ ЛЕЖАТ ФАЙЛЫ:")
    print("  backend :", BACKEND_CSV)
    print("  backend :", BACKEND_SUMMARY)
    print("  frontend:", FRONTEND_EVENTS)
    print("  frontend:", FRONTEND_SESSIONS)
    print("\nМетрики также доступны по адресу:  {BACKEND_URL}/metrics  (JSON)")


if __name__ == "__main__":
    main()
