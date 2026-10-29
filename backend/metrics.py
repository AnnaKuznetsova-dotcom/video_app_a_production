"""
Модуль сбора технических метрик бэкенда (Yandex Serverless Container).

Хранение — ТОЛЬКО CSV (просто открыть в Excel / Pandas). Никакого SQLite.

Измеряемые метрики:
    - Latency (total_ms):        общее время обработки запроса /generate/.
    - Render Time (render_ms):   время именно склейки видео.
    - Download (download_ms):    время скачивания фрагментов из S3.
    - Error Rate:                доля запросов, завершившихся ошибкой.
    - Стоимость инференса:       оценка стоимости CPU-секунд рендера.
    - DS-данные:                 предсказанный класс, топ-SHAP-факторы,
                                 число скачанных фрагментов.

Где смотреть:
    backend/data_metrics/metrics.csv  — построчные записи (каждый инференс).
    backend/data_metrics/summary.csv  — сверка агрегатов (перезаписывается).

Никакого SQL-клиента не нужно: открывайте metrics.csv в Excel
(Файл -> Открыть -> Выберите файл типа "Все файлы (*.*)") или так:
    python -c "import pandas as pd; print(pd.read_csv('backend/data_metrics/metrics.csv'))"
"""

import csv
import os
import threading
import time
from typing import Any

METRICS_DIR = os.getenv(
    "METRICS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_metrics")
)
CSV_PATH = os.getenv("METRICS_CSV", os.path.join(METRICS_DIR, "metrics.csv"))
SUMMARY_CSV_PATH = os.getenv("METRICS_SUMMARY_CSV", os.path.join(METRICS_DIR, "summary.csv"))
# Frontend-события для Спирмена: локальный путь (если задан) или копия из S3.
FRONTEND_EVENTS_CSV = os.getenv(
    "FRONTEND_EVENTS_CSV", os.path.join(METRICS_DIR, "frontend_events.csv")
)
# Копия событий из S3 при перезапуске контейнера.
FRONTEND_S3_KEY = os.getenv("FRONTEND_S3_KEY", "metrics_frontend/events.csv")

# --- Долговременное хранение метрик в S3 (чтобы не терять при перезапуске
#     Serverless Container). Работает только если заданы S3-переменные окружения
#     (те же, что и для main.py). Если их нет — просто работаем локально. ---
S3_ENDPOINT = os.getenv("YC_S3_ENDPOINT", "https://storage.yandexcloud.net")
BUCKET_NAME = os.getenv("BUCKET_NAME")
S3_KEY_ID = os.getenv("YC_ACCESS_KEY_ID")
S3_SECRET = os.getenv("YC_SECRET_ACCESS_KEY")
# Префикс папки метрик в бакете (например: "metrics/")
METRICS_S3_PREFIX = os.getenv("METRICS_S3_PREFIX", "metrics/").rstrip("/") + "/"
SYNC_ENABLED = all([BUCKET_NAME, S3_KEY_ID, S3_SECRET])

# Ориентировочная цена CPU-секунды (USD). Для Yandex Serverless Containers
# ≈ $5 за 1 млн CPU-секунд → 0.000005 USD/сек. Подставьте свой тариф.
CPU_SECOND_PRICE_USD = float(os.getenv("CPU_SECOND_PRICE_USD", "0.000005"))

_lock = threading.Lock()
_s3_client = None
_sync_lock = threading.Lock()

CSV_HEADER = [
    "ts_iso",
    "endpoint",
    "settlement",
    "klass",
    "top_factors",
    "fragments_used",
    "download_ms",
    "render_ms",
    "total_ms",
    "shap_mismatch_groups",
    "success",
    "error",
    "groups_unique",
    "variant",
    "preprocess_ms",
    "predict_ms",
    "shap_ms",
    "model_load_ms",
    "is_cold",
]


# ---------------------------------------------------------------------------
# Синхронизация с S3 (опционально)
# ---------------------------------------------------------------------------
def _get_s3():
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.session.Session().client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_KEY_ID,
            aws_secret_access_key=S3_SECRET,
        )
    return _s3_client


def restore_metrics_from_s3() -> None:
    """На старте скачивает накопленный metrics.csv из S3, чтобы метрики
    продолжали копиться, а не обнулялись после рестарта контейнера."""
    if not SYNC_ENABLED or os.path.exists(CSV_PATH):
        return
    try:
        with _sync_lock:
            os.makedirs(METRICS_DIR, exist_ok=True)
            _get_s3().download_file(
                Bucket=BUCKET_NAME,
                Key=f"{METRICS_S3_PREFIX}metrics.csv",
                Filename=CSV_PATH,
            )
            print("[metrics] restored metrics.csv from S3")
    except Exception:
        # Файла в S3 ещё нет (первый запуск) — это нормально.
        pass


def sync_metrics_to_s3() -> None:
    """Загружает локальные CSV-метрики в S3 (папка metrics/)."""
    if not SYNC_ENABLED:
        return
    if not os.path.exists(CSV_PATH):
        return
    try:
        with _sync_lock:
            client = _get_s3()
            for local, remote in (
                (CSV_PATH, f"{METRICS_S3_PREFIX}metrics.csv"),
                (SUMMARY_CSV_PATH, f"{METRICS_S3_PREFIX}summary.csv"),
            ):
                if os.path.exists(local):
                    client.upload_file(
                        Bucket=BUCKET_NAME,
                        Key=remote,
                        Filename=local,
                        ExtraArgs={"ContentType": "text/csv; charset=utf-8"},
                    )
    except Exception as exc:
        print(f"[metrics] S3 sync failed (non-fatal): {exc}")


def reset_metrics() -> dict[str, Any]:
    """Полный сброс метрик: удаляет локальные CSV и их копии в S3.

    Используется admin-эндпоинтом для начала сбора «с чистого листа».
    Возвращает словарь с результатом (для ответа эндпоинта).
    """
    removed_local = []
    for path in (CSV_PATH, SUMMARY_CSV_PATH):
        try:
            if os.path.exists(path):
                os.remove(path)
                removed_local.append(os.path.basename(path))
        except Exception as exc:
            print(f"[metrics] reset remove local failed {path}: {exc}")
    removed_s3 = []
    if SYNC_ENABLED:
        try:
            with _sync_lock:
                client = _get_s3()
                for remote in (
                    f"{METRICS_S3_PREFIX}metrics.csv",
                    f"{METRICS_S3_PREFIX}summary.csv",
                ):
                    client.delete_object(Bucket=BUCKET_NAME, Key=remote)
                    removed_s3.append(remote)
        except Exception as exc:
            print(f"[metrics] reset S3 delete failed (non-fatal): {exc}")
    print("[metrics] reset done:", {"local": removed_local, "s3": removed_s3})
    return {"local_removed": removed_local, "s3_removed": removed_s3}


def _ensure_frontend_events() -> str | None:
    """Возвращает путь к файлу frontend-событий (для Спирмена). Локальный путь
    приоритетен; иначе забираем копию metrics_frontend/events.csv из S3."""
    if os.path.exists(FRONTEND_EVENTS_CSV) and os.path.getsize(FRONTEND_EVENTS_CSV) > 0:
        return FRONTEND_EVENTS_CSV
    if not SYNC_ENABLED:
        return None
    try:
        with _sync_lock:
            os.makedirs(METRICS_DIR, exist_ok=True)
            _get_s3().download_file(
                Bucket=BUCKET_NAME,
                Key=FRONTEND_S3_KEY,
                Filename=FRONTEND_EVENTS_CSV,
            )
            print("[metrics] restored frontend events.csv from S3")
        return FRONTEND_EVENTS_CSV if os.path.getsize(FRONTEND_EVENTS_CSV) > 0 else None
    except Exception:
        return None


def compute_spearman_rho() -> dict[str, Any] | None:
    """Spearman ρ между SHAP-порядком фрагментов и временем просмотра каждого
    фрагмента (данные плеера — frontend-события video_segment_watch).

    Возвращает {"rho": float, "videos": int} либо None, если данных нет.
    Усредняем ρ по всем роликам, где видео досматривалось по сегментам.
    """
    path = _ensure_frontend_events()
    if not path:
        return None
    import json as _json

    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("event_type") != "video_segment_watch":
                continue
            try:
                d = _json.loads(r.get("extra") or "{}")
            except Exception:
                continue
            names = d.get("segment_names") or []
            watch = d.get("watched_per_segment") or []
            if not names or not watch or len(names) != len(watch):
                continue
            # «Общий вид» — не SHAP-фактор, исключаем.
            idx = [i for i, n in enumerate(names) if str(n).strip().lower() != "общий вид"]
            if len(idx) < 2:
                continue
            shap_rank = list(range(len(idx)))
            watch_vals = [watch[i] for i in idx]
            order = sorted(range(len(watch_vals)), key=lambda i: watch_vals[i], reverse=True)
            watch_rank = [0] * len(watch_vals)
            for ri, oi in enumerate(order):
                watch_rank[oi] = ri
            n = len(shap_rank)
            mx = sum(shap_rank) / n
            my = sum(watch_rank) / n
            num = sum((a - mx) * (b - my) for a, b in zip(shap_rank, watch_rank, strict=False))
            den = (
                sum((a - mx) ** 2 for a in shap_rank) * sum((b - my) ** 2 for b in watch_rank)
            ) ** 0.5
            if den == 0:
                continue
            rows.append(num / den)
    if not rows:
        return None
    return {"rho": round(sum(rows) / len(rows), 4), "videos": len(rows)}


def metrics_backup_info() -> dict[str, Any]:
    """Информация о резервном хранении (для эндпоинта /metrics и логов)."""
    return {
        "s3_enabled": SYNC_ENABLED,
        "s3_prefix": METRICS_S3_PREFIX if SYNC_ENABLED else None,
        "bucket": BUCKET_NAME if SYNC_ENABLED else None,
        "remote_csv": f"{METRICS_S3_PREFIX}metrics.csv" if SYNC_ENABLED else None,
    }


def log_inference(
    *,
    endpoint: str,
    settlement: str | None = None,
    klass: int | None = None,
    top_factors: list | None = None,
    fragments_used: int = 0,
    download_ms: int = 0,
    render_ms: int = 0,
    total_ms: int = 0,
    shap_mismatch_groups: list | None = None,
    groups_unique: bool = True,
    variant: str | None = None,
    preprocess_ms: int = 0,
    predict_ms: int = 0,
    shap_ms: int = 0,
    model_load_ms: int = 0,
    is_cold: bool = False,
    success: bool = True,
    error: str | None = None,
    skip_log: bool = False,
) -> None:
    """Однократная запись результата одного инференса в CSV (+ sync в S3).

    Если skip_log=True — запись пропускается (используется тестами, чтобы не
    засорять метрики фиктивными вызовами /generate/).
    """
    if skip_log:
        return
    import json

    _restore_once()
    _ensure_header()
    try:
        with _lock:
            os.makedirs(METRICS_DIR, exist_ok=True)
            new_file = not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0
            row = [
                time.strftime("%Y-%m-%dT%H:%M:%S"),
                endpoint,
                settlement or "",
                klass if klass is not None else "",
                json.dumps(top_factors, ensure_ascii=False) if top_factors else "",
                fragments_used,
                download_ms,
                render_ms,
                total_ms,
                (
                    json.dumps(shap_mismatch_groups, ensure_ascii=False)
                    if shap_mismatch_groups
                    else ""
                ),
                1 if success else 0,
                (error or "")[:500],
                1 if groups_unique else 0,
                variant or "",
                preprocess_ms,
                predict_ms,
                shap_ms,
                model_load_ms,
                1 if is_cold else 0,
            ]
            with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(CSV_HEADER)
                writer.writerow(row)
            _write_summary()
        # Загружаем свежие метрики в S3 (не блокируем пользователя).
        if SYNC_ENABLED:
            threading.Thread(target=sync_metrics_to_s3, daemon=True).start()
    except Exception:
        # Метрики никогда не роняют основной запрос.
        pass


_restored_once = False


def _restore_once():
    global _restored_once
    if not _restored_once:
        _restored_once = True
        restore_metrics_from_s3()


# ---------------------------------------------------------------------------
# Сводка — перезаписываемый CSV с агрегатами
# ---------------------------------------------------------------------------
# --- ИСТОРИЯ ФОРМАТА metrics.csv (важно для чтения старых файлов):
#   v1 (11 колонок):  [.., total_ms, success, error]
#   v2 (12 колонок):  [.., total_ms, shap_mismatch_groups, success, error]
#   v3 (13 колонок):  [.., total_ms, shap_mismatch_groups, success, error, groups_unique]
# Некоторые восстановленные из S3 файлы имеют СТАРЫЙ заголовок при НОВЫХ
# строках (заголовок не переписывался при дописывании). Поэтому колонки
# определяем ПО ЧИСЛУ полей в каждой строке, а не по первой строке файла.
_METRIC_BASE = [
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


def _map_csv_row(ln: list[str]) -> dict[str, Any]:
    d = dict(zip(_METRIC_BASE, ln[:9], strict=False))
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
    # Новая версия (v4): variant + хронометраж этапов + признак cold-start.
    if n >= 19:
        d["variant"] = ln[13]
        d["preprocess_ms"] = ln[14]
        d["predict_ms"] = ln[15]
        d["shap_ms"] = ln[16]
        d["model_load_ms"] = ln[17]
        d["is_cold"] = ln[18]
    else:
        d["variant"] = ""
        d["preprocess_ms"] = ""
        d["predict_ms"] = ""
        d["shap_ms"] = ""
        d["model_load_ms"] = ""
        d["is_cold"] = ""
    return d


def _load_rows() -> list[dict[str, Any]]:
    if not os.path.exists(CSV_PATH):
        return []
    rows = []
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # заголовок
        for ln in reader:
            if not ln or (len(ln) == 1 and not ln[0].strip()):
                continue
            rows.append(_map_csv_row(ln))
    return rows


# --- Проверка заголовка CSV. Если на диске файл со СТАРОЙ шапкой (например,
#     восстановленный из S3 до добавления колонки groups_unique), новая строка
#     сместит колонки. Поэтому при обнаружении несовпадения шапку пересоздаём. ---
def _ensure_header() -> None:
    expected = ",".join(CSV_HEADER)
    try:
        if not os.path.exists(CSV_PATH) or os.path.getsize(CSV_PATH) == 0:
            return
        with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
            first_line = f.readline().strip()
        if first_line == expected:
            return
        # Старый файл: читаем все строки через НАДЁЖНЫЙ парсер (по числу полей),
        # затем перезаписываем в канонический формат (заголовок = CSV_HEADER).
        rows = _load_rows()
        with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        print("[metrics] CSV header migrated to:", expected, f"(rows={len(rows)})")
    except Exception as exc:
        print(f"[metrics] header check skipped (non-fatal): {exc}")


# --- Описание и формула каждой метрики (пишутся в summary.csv колонками). ---
METRIC_COMMENTS: dict[str, dict[str, str]] = {
    "total_inferences": {
        "desc": "Всего запросов генерации, записанных в metrics.csv",
        "formula": "count(строк metrics.csv)",
    },
    "success": {
        "desc": "Успешных инференсов (получен готовый ролик)",
        "formula": "count(success='1')",
    },
    "errors": {
        "desc": "Инференсов с ошибкой (исключение при генерации)",
        "formula": "count(success='0')",
    },
    "error_rate_pct_rounded_2": {
        "desc": "Доля запросов, завершившихся ошибкой",
        "formula": "errors / total * 100",
    },
    "shap_mismatch_inferences": {
        "desc": "Успешных инференсов, где выбор клиента != максимум |SHAP| хотя бы в одной группе",
        "formula": "sum(1 if shap_mismatch_groups не пуст)",
    },
    "shap_mismatch_total_groups": {
        "desc": "Суммарное число групп с расхождением «клиент vs модель» по всем инференсам",
        "formula": "sum(len(shap_mismatch_groups))",
    },
    "dominant_feature_precision_dfp": {
        "desc": "DFP: доля инференсов БЕЗ расхождений клиент-модель (по всем 4 группам сразу)",
        "formula": "(success − shap_mismatch_inferences) / success",
    },
    "share_high_confidence_predictions": {
        "desc": "High Confidence: доля инференсов, где модель УВЕРЕНА в выборе клиента — max|SHAP| по группе совпал с выбором клиента ИЛИ разница |max−chosen| < порога (0.5*max). Сигнал доверия рекомендации.",
        "formula": "sum(уверенных) / success, где уверен = для всех групп (chosen==max) или (|max_shap−chosen_shap| < 0.5*max_shap)",
    },
    "hit_ratio_top3_factors": {
        "desc": "Доля ГРУПП (не инференсов!), где выбранный клиентом фактор = максимум SHAP",
        "formula": "1 − shap_mismatch_total_groups / (success * 4)",
    },
    "groups_unique_rate": {
        "desc": "Доля роликов без дублей групп (один клип на группу)",
        "formula": "count(groups_unique != 0) / success",
    },
    "groups_duplicate_inferences": {
        "desc": "Роликов с дублем группы (баг сборки)",
        "formula": "success − count(groups_unique != 0)",
    },
    "latency_ms_avg": {
        "desc": "Средняя полная задержка генерации ролика (клиент → ролик)",
        "formula": "mean(total_ms) по успешным",
    },
    "latency_ms_p50": {
        "desc": "Медианная задержка генерации ролика",
        "formula": "p50(total_ms)",
    },
    "latency_ms_p95": {
        "desc": "95-й перцентиль задержки генерации ролика",
        "formula": "p95(total_ms)",
    },
    "latency_ms_p50_cold": {
        "desc": "p50 задержки для ХОЛОДНОГО старта (первый инференс после старта контейнера)",
        "formula": "p50(total_ms) где is_cold=1",
    },
    "latency_ms_p95_cold": {
        "desc": "p95 задержки для ХОЛОДНОГО старта",
        "formula": "p95(total_ms) где is_cold=1",
    },
    "latency_ms_p50_warm": {
        "desc": "p50 задержки для ПОВТОРНЫХ запусков (warm)",
        "formula": "p50(total_ms) где is_cold=0",
    },
    "latency_ms_p95_warm": {
        "desc": "p95 задержки для ПОВТОРНЫХ запусков (warm)",
        "formula": "p95(total_ms) где is_cold=0",
    },
    "stage_preprocess_ms_p50_cold": {
        "desc": "p50 времени preprocessing (восстановление вектора) — холодный старт",
        "formula": "p50(preprocess_ms) где is_cold=1",
    },
    "stage_preprocess_ms_p95_cold": {
        "desc": "p95 времени preprocessing — холодный старт",
        "formula": "p95(preprocess_ms) где is_cold=1",
    },
    "stage_preprocess_ms_p50_warm": {
        "desc": "p50 времени preprocessing — повторный запуск",
        "formula": "p50(preprocess_ms) где is_cold=0",
    },
    "stage_preprocess_ms_p95_warm": {
        "desc": "p95 времени preprocessing — повторный запуск",
        "formula": "p95(preprocess_ms) где is_cold=0",
    },
    "stage_predict_ms_p50_cold": {
        "desc": "p50 времени prediction — холодный старт",
        "formula": "p50(predict_ms) где is_cold=1",
    },
    "stage_predict_ms_p95_cold": {
        "desc": "p95 времени prediction — холодный старт",
        "formula": "p95(predict_ms) где is_cold=1",
    },
    "stage_predict_ms_p50_warm": {
        "desc": "p50 времени prediction — повторный запуск",
        "formula": "p50(predict_ms) где is_cold=0",
    },
    "stage_predict_ms_p95_warm": {
        "desc": "p95 времени prediction — повторный запуск",
        "formula": "p95(predict_ms) где is_cold=0",
    },
    "stage_shap_ms_p50_cold": {
        "desc": "p50 времени SHAP-объяснения — холодный старт",
        "formula": "p50(shap_ms) где is_cold=1",
    },
    "stage_shap_ms_p95_cold": {
        "desc": "p95 времени SHAP-объяснения — холодный старт",
        "formula": "p95(shap_ms) где is_cold=1",
    },
    "stage_shap_ms_p50_warm": {
        "desc": "p50 времени SHAP-объяснения — повторный запуск",
        "formula": "p50(shap_ms) где is_cold=0",
    },
    "stage_shap_ms_p95_warm": {
        "desc": "p95 времени SHAP-объяснения — повторный запуск",
        "formula": "p95(shap_ms) где is_cold=0",
    },
    "stage_model_load_ms_max": {
        "desc": "Время ЗАГРУЗКИ модели (model+explainer) при старте контейнера",
        "formula": "max(model_load_ms)",
    },
    "cold_inference_count": {
        "desc": "Число холодных инференсов (первый после старта) в периоде",
        "formula": "count(is_cold=1)",
    },
    "warm_inference_count": {
        "desc": "Число повторных (warm) инференсов в периоде",
        "formula": "count(is_cold=0)",
    },
    "variants_logged": {
        "desc": "Количество уникальных идентификаторов версий сценария, попавших в метрики",
        "formula": "len(unique(variant))",
    },
    "render_ms_avg": {
        "desc": "Среднее время склейки видео (ffmpeg + mux)",
        "formula": "mean(render_ms)",
    },
    "render_ms_p95": {
        "desc": "95-й перцентиль времени склейки видео",
        "formula": "p95(render_ms)",
    },
    "download_ms_avg": {
        "desc": "Среднее время скачивания фрагментов из S3",
        "formula": "mean(download_ms)",
    },
    "est_cost_per_inference_usd": {
        "desc": "Оценка стоимости генерации одного ролика (CPU-секунды)",
        "formula": "sum(render_ms)/1000 * CPU_SECOND_PRICE_USD / success",
    },
    "est_cost_usd_total": {
        "desc": "Суммарная оценка стоимости всех успешных генераций",
        "formula": "sum(render_ms)/1000 * CPU_SECOND_PRICE_USD",
    },
    "cpu_second_price_usd": {
        "desc": "Тариф CPU-секунды (USD), задаётся env",
        "formula": "CPU_SECOND_PRICE_USD",
    },
    "accuracy_classifier": {
        "desc": "Точность классификатора ЖК на размеченном тест-сете. NA: нужна ручная разметка ground-truth сделок.",
        "formula": "TP+TN / (TP+TN+FP+FN) по тест-сету",
    },
    "spearman_rho_shap_vs_watchtime": {
        "desc": "Spearman ρ между SHAP-порядком фрагментов и временем просмотра сегмента (данные плеера). NA: нет событий video_segment_watch.",
        "formula": "среднее по роликам корреляции рангов: порядок ranked_factors vs watched_per_segment",
    },
    "video_quality_pass_rate_qar": {
        "desc": "Доля роликов, прошедших ручную проверку качества (QAR). NA: нужна ручная/MTurk проверка.",
        "formula": "passed / checked (вручную)",
    },
    "updated_at": {
        "desc": "Время формирования сводки",
        "formula": "UTC now",
    },
}


def _write_summary() -> None:
    _restore_once()
    _ensure_header()
    rows = _load_rows()
    if not rows:
        return
    total = len(rows)
    errors = [r for r in rows if r.get("success") == "0"]
    ok_rows = [r for r in rows if r.get("success") == "1"]

    def avg(field):
        vals = [int(r[field]) for r in ok_rows if (r.get(field) or "").isdigit()]
        return round(sum(vals) / len(vals)) if vals else ""

    def percentile(field, p):
        vals = sorted(int(r[field]) for r in ok_rows if (r.get(field) or "").isdigit())
        if not vals:
            return ""
        k = int((len(vals) - 1) * p)
        return vals[k]

    def _rows_for(cold):
        """Срез записей по признаку холодного запуска (True/False/None=все)."""
        if cold is None:
            return ok_rows
        want = "1" if cold else "0"
        return [r for r in ok_rows if (r.get("is_cold") or "") == want]

    def extentile(rows, field, p):
        vals = sorted(int(r[field]) for r in rows if (r.get(field) or "").isdigit())
        if not vals:
            return ""
        return vals[int((len(vals) - 1) * p)]

    cold_rows = _rows_for(True)
    warm_rows = _rows_for(False)
    stage_stats = {}
    for stage in ("preprocess", "predict", "shap"):
        for p, plabel in ((0.5, "p50"), (0.95, "p95")):
            stage_stats[f"stage_{stage}_ms_{plabel}_warm"] = extentile(warm_rows, f"{stage}_ms", p)
            stage_stats[f"stage_{stage}_ms_{plabel}_cold"] = extentile(cold_rows, f"{stage}_ms", p)

    cost_cpu_s = sum(int(r.get("render_ms") or 0) for r in ok_rows) / 1000.0
    cost_usd = cost_cpu_s * CPU_SECOND_PRICE_USD

    # Task 8: статистика «выбор клиента != максимум SHAP по группе» —
    # важный сигнал качества модели/классификации (чтобы заметить системные огрехи).
    import json as _json

    mismatch_inferences = 0
    mismatch_total_groups = 0
    for r in ok_rows:
        raw = (r.get("shap_mismatch_groups") or "").strip()
        if not raw:
            continue
        try:
            parsed = _json.loads(raw)
        except Exception:
            parsed = []
        if isinstance(parsed, list) and parsed:
            mismatch_inferences += 1
            mismatch_total_groups += len(parsed)

    ok_total = len(ok_rows)
    # Дубли групп в одном ролике (запрещено: один клип на группу).
    # Отдельные записи (generations) с >1 клипом из одной группы — баг сборки.
    groups_unique_count = sum(1 for r in ok_rows if r.get("groups_unique", "1") != "0")
    groups_unique_rate = round(groups_unique_count / ok_total, 4) if ok_total else ""

    # DFP (Dominant Feature Precision): доля инференсов, где во ВСЕХ группах
    # выбранный пользователем приоритет — максимум |SHAP| (без разночтений).
    dfp = round((ok_total - mismatch_inferences) / ok_total, 4) if ok_total else ""

    # Hit Ratio Top-3 (per-group): доля ГРУПП, где выбранный признак = максимум SHAP.
    # Отличается от DFP: DFP считает «все группы ОК» (на уровне инференса),
    # Hit Ratio считает «эта группа ОК» (на уровне отдельной группы).
    # 4 группы на каждый инференс: flat_plan, priorities, finishing, children.
    NUM_GROUPS_PER_INFERENCE = 4
    total_groups = ok_total * NUM_GROUPS_PER_INFERENCE
    matched_groups = total_groups - mismatch_total_groups
    hit_ratio = round(matched_groups / total_groups, 4) if total_groups else ""

    # High Confidence (НЕЗАВИСИМАЯ метрика, не дублирует DFP): инференс считается
    # "высокоуверенным", если модель согласна с клиентом: в каждой группе либо
    # выбранный признак = максимум |SHAP|, либо расхождение мало
    # (|max_shap − chosen_shap| < 0.50*max_shap), т.е. модель почти уверена.
    # Отличие от DFP: DFP требует ПОЛНОГО совпадения; HighConf допускает
    # незначительный зазор — это доля «рекомендаций, которым можно верить».
    HIGH_CONF_MARGIN_RATIO = 0.50
    high_conf_inferences = 0
    for r in ok_rows:
        raw = (r.get("shap_mismatch_groups") or "").strip()
        if not raw:
            high_conf_inferences += 1
            continue
        try:
            parsed = _json.loads(raw)
        except Exception:
            parsed = []
        confident = True
        for g in parsed if isinstance(parsed, list) else []:
            try:
                mx = abs(float(g.get("max_shap") or 0.0))
                cs = abs(float(g.get("chosen_shap") or 0.0))
            except Exception:
                mx, cs = 0.0, 0.0
            if mx > 0 and (mx - cs) >= HIGH_CONF_MARGIN_RATIO * mx:
                confident = False
                break
        if confident:
            high_conf_inferences += 1
    high_conf = round(high_conf_inferences / ok_total, 4) if ok_total else ""

    # Spearman ρ (frontend-телеметрия плеера; из S3 metrics_frontend/events.csv).
    spearman_raw = compute_spearman_rho()
    if spearman_raw:
        spearman_val = f"{spearman_raw['rho']} (n={spearman_raw['videos']})"
    else:
        spearman_val = "NA"

    summary = {
        "total_inferences": total,
        "success": len(ok_rows),
        "errors": len(errors),
        "error_rate_pct_rounded_2": round(100.0 * len(errors) / total, 2) if total else "",
        "shap_mismatch_inferences": mismatch_inferences,
        "shap_mismatch_total_groups": mismatch_total_groups,
        "dominant_feature_precision_dfp": dfp,
        "share_high_confidence_predictions": high_conf,
        "hit_ratio_top3_factors": hit_ratio,
        "groups_unique_rate": groups_unique_rate,
        "groups_duplicate_inferences": ok_total - groups_unique_count,
        "latency_ms_avg": avg("total_ms"),
        "latency_ms_p50": percentile("total_ms", 0.5),
        "latency_ms_p95": percentile("total_ms", 0.95),
        "latency_ms_p50_cold": extentile(cold_rows, "total_ms", 0.5),
        "latency_ms_p95_cold": extentile(cold_rows, "total_ms", 0.95),
        "latency_ms_p50_warm": extentile(warm_rows, "total_ms", 0.5),
        "latency_ms_p95_warm": extentile(warm_rows, "total_ms", 0.95),
        "render_ms_avg": avg("render_ms"),
        "render_ms_p95": percentile("render_ms", 0.95),
        "download_ms_avg": avg("download_ms"),
        "stage_model_load_ms_max": max(
            (
                int(r.get("model_load_ms") or 0)
                for r in ok_rows
                if (r.get("model_load_ms") or "").isdigit()
            ),
            default="",
        ),
        "cold_inference_count": len(cold_rows),
        "warm_inference_count": len(warm_rows),
        "variants_logged": len({r.get("variant") for r in ok_rows if r.get("variant")}),
        **stage_stats,
        "est_cost_per_inference_usd": round(cost_usd / ok_total, 8) if ok_total else "",
        "est_cost_usd_total": round(cost_usd, 6),
        "cpu_second_price_usd": CPU_SECOND_PRICE_USD,
        # Метрики, требующие ВНЕШНИХ источников данных (заполняются офлайн/вручную):
        "accuracy_classifier": "NA",  # нужен размеченный тест-сет
        "spearman_rho_shap_vs_watchtime": spearman_val,
        "video_quality_pass_rate_qar": "NA",  # нужна ручная/MTurk проверка роликов
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        os.makedirs(METRICS_DIR, exist_ok=True)
        with open(SUMMARY_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value", "description", "formula"])
            for k, v in summary.items():
                meta = METRIC_COMMENTS.get(k, {"desc": "", "formula": ""})
                writer.writerow([k, v, meta["desc"], meta["formula"]])
    except Exception:
        pass


def summary() -> dict[str, Any]:
    """Возвращает свежую сводку (также используется эндпоинтом /metrics)."""
    _write_summary()
    result = {"s3_backup": metrics_backup_info()}
    if not os.path.exists(SUMMARY_CSV_PATH):
        result["note"] = "no metrics yet"
        return result
    with open(SUMMARY_CSV_PATH, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r.get("metric") and r.get("metric") != "metric"]
        result.update({r["metric"]: r["value"] for r in rows})
    return result
