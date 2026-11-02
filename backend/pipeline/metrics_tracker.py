"""Этап 6 — Сбор технических метрик инференса (CSV + бэкап в S3).

Хранение — ТОЛЬКО CSV (просто открыть в Excel / Pandas). Никакого SQLite.

Измеряемые метрики:
    - Latency (total_ms):        общее время обработки запроса.
    - Preprocess (preprocess_ms): восстановление вектора признаков.
    - Prediction (predict_ms):   инференс модели.
    - Download (download_ms):    время обращения к S3 (если было).
    - Error Rate:                доля запросов, завершившихся ошибкой.
    - Стоимость инференса:       оценка стоимости CPU-секунд.
    - Cold/warm split:           первый запрос после старта контейнера — отдельно.

Где смотреть:
    backend/data_metrics/metrics.csv  — построчные записи (каждый инференс).
    backend/data_metrics/summary.csv  — сводка агрегатов (перезаписывается).

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
    "METRICS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_metrics"),
)
CSV_PATH = os.getenv("METRICS_CSV", os.path.join(METRICS_DIR, "metrics.csv"))
SUMMARY_CSV_PATH = os.getenv("METRICS_SUMMARY_CSV", os.path.join(METRICS_DIR, "summary.csv"))

# --- Долговременное хранение метрик в S3 (чтобы не терять при перезапуске
#     Serverless Container). Работает только если заданы S3-переменные окружения.
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

# История схем metrics.csv — v5 актуальна:
#   v1 (11 колонок):  [ts_iso..total_ms, success, error]           (legacy)
#   v2 (12 колонок):  [.., shap_mismatch, success, error]          (legacy, SHAP удалён)
#   v3 (13 колонок):  [.., groups_unique]                          (legacy, SHAP удалён)
#   v4 (19 колонок):  [.., variant, этапы хронометража, is_cold]   (legacy, SHAP удалён)
#   v5 (15 колонок):  [ts_iso..total_ms, success, error, variant, preprocess_ms,
#                      predict_ms, model_load_ms, is_cold]
CSV_HEADER = [
    "ts_iso",
    "endpoint",
    "settlement",
    "klass",
    "fragments_used",
    "download_ms",
    "render_ms",
    "total_ms",
    "success",
    "error",
    "variant",
    "preprocess_ms",
    "predict_ms",
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


def log_inference(
    *,
    endpoint: str,
    settlement: str | None = None,
    klass: int | None = None,
    fragments_used: int = 1,
    download_ms: int = 0,
    render_ms: int = 0,
    total_ms: int = 0,
    variant: str | None = None,
    preprocess_ms: int = 0,
    predict_ms: int = 0,
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
                fragments_used,
                download_ms,
                render_ms,
                total_ms,
                1 if success else 0,
                (error or "")[:500],
                variant or "",
                preprocess_ms,
                predict_ms,
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
# --- Чтение metrics.csv: колонки определяем ПО ЧИСЛУ полей в каждой строке,
#     а не по заголовку (старые файлы из S3 могут иметь легаси-шапку).
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
_METRIC_BASE_V5 = _METRIC_BASE[:4] + _METRIC_BASE[5:]


def _map_csv_row(ln: list[str]) -> dict[str, Any]:
    n = len(ln)
    if n == 15:  # v5: актуальная схема (SHAP-колонки удалены)
        d = dict(zip(_METRIC_BASE_V5, ln[:8], strict=False))
        d["success"] = ln[8]
        d["error"] = ln[9]
        d["variant"] = ln[10]
        d["preprocess_ms"] = ln[11]
        d["predict_ms"] = ln[12]
        d["model_load_ms"] = ln[13]
        d["is_cold"] = ln[14]
        return d
    # legacy (v1..v4): 9 базовых колонок с top_factors на позиции 4
    d = dict(zip(_METRIC_BASE, ln[:9], strict=False))
    if n >= 12:
        d["success"] = ln[10]
        d["error"] = ln[11]
    else:
        d["success"] = ln[9] if n >= 10 else ""
        d["error"] = ln[10] if n >= 11 else ""
    if n >= 19:  # блок хронометража v4: variant, preprocess, predict, shap, model_load, is_cold
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
#     восстановленный из S3 до изменения схемы), новая строка сместит колонки.
#     Поэтому при обнаружении несовпадения шапку пересоздаём. ---
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
    "latency_ms_avg": {
        "desc": "Средняя полная задержка генерации ролика (клиент → ролик)",
        "formula": "mean(total_ms) по успешным",
    },
    "latency_ms_p50": {"desc": "Медианная задержка генерации ролика", "formula": "p50(total_ms)"},
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
    "stage_model_load_ms_max": {
        "desc": "Время ЗАГРУЗКИ модели при старте контейнера",
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
    "video_quality_pass_rate_qar": {
        "desc": "Доля роликов, прошедших ручную проверку качества (QAR). NA: нужна ручная/MTurk проверка.",
        "formula": "passed / checked (вручную)",
    },
    "updated_at": {
        "desc": "Время формирования сводки",
        "formula": "UTC now",
    },
}


def _avg_ms(rows: list[dict], field: str):
    vals = [int(r[field]) for r in rows if (r.get(field) or "").isdigit()]
    return round(sum(vals) / len(vals)) if vals else ""


def _pct_ms(rows: list[dict], field: str, p: float):
    vals = sorted(int(r[field]) for r in rows if (r.get(field) or "").isdigit())
    if not vals:
        return ""
    return vals[int((len(vals) - 1) * p)]


def _rows_for_cold(ok_rows: list[dict], cold: bool | None) -> list[dict]:
    """Срез записей по признаку холодного запуска (True/False/None=все)."""
    if cold is None:
        return ok_rows
    want = "1" if cold else "0"
    return [r for r in ok_rows if (r.get("is_cold") or "") == want]


def _stage_percentiles(cold_rows: list[dict], warm_rows: list[dict]) -> dict:
    """p50/p95 по стадиям preprocess/predict отдельно для cold и warm."""
    stage_stats = {}
    for stage in ("preprocess", "predict"):
        for p, plabel in ((0.5, "p50"), (0.95, "p95")):
            stage_stats[f"stage_{stage}_ms_{plabel}_warm"] = _pct_ms(warm_rows, f"{stage}_ms", p)
            stage_stats[f"stage_{stage}_ms_{plabel}_cold"] = _pct_ms(cold_rows, f"{stage}_ms", p)
    return stage_stats


def _write_summary() -> None:
    _restore_once()
    _ensure_header()
    rows = _load_rows()
    if not rows:
        return
    total = len(rows)
    errors = [r for r in rows if r.get("success") == "0"]
    ok_rows = [r for r in rows if r.get("success") == "1"]

    cold_rows = _rows_for_cold(ok_rows, True)
    warm_rows = _rows_for_cold(ok_rows, False)
    stage_stats = _stage_percentiles(cold_rows, warm_rows)

    ok_total = len(ok_rows)
    cost_cpu_s = sum(int(r.get("render_ms") or 0) for r in ok_rows) / 1000.0
    cost_usd = cost_cpu_s * CPU_SECOND_PRICE_USD

    summary = {
        "total_inferences": total,
        "success": len(ok_rows),
        "errors": len(errors),
        "error_rate_pct_rounded_2": round(100.0 * len(errors) / total, 2) if total else "",
        "latency_ms_avg": _avg_ms(ok_rows, "total_ms"),
        "latency_ms_p50": _pct_ms(ok_rows, "total_ms", 0.5),
        "latency_ms_p95": _pct_ms(ok_rows, "total_ms", 0.95),
        "latency_ms_p50_cold": _pct_ms(cold_rows, "total_ms", 0.5),
        "latency_ms_p95_cold": _pct_ms(cold_rows, "total_ms", 0.95),
        "latency_ms_p50_warm": _pct_ms(warm_rows, "total_ms", 0.5),
        "latency_ms_p95_warm": _pct_ms(warm_rows, "total_ms", 0.95),
        "render_ms_avg": _avg_ms(ok_rows, "render_ms"),
        "render_ms_p95": _pct_ms(ok_rows, "render_ms", 0.95),
        "download_ms_avg": _avg_ms(ok_rows, "download_ms"),
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
        "video_quality_pass_rate_qar": "NA",  # нужна ручная/MTurk проверка роликов
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _write_summary_csv(summary)


def _write_summary_csv(summary: dict[str, Any]) -> None:
    """Пишет сводку в SUMMARY_CSV_PATH (metric | value | description | formula)."""
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


def metrics_backup_info() -> dict[str, Any]:
    """Информация о резервном хранении (для эндпоинта /metrics и логов)."""
    return {
        "s3_enabled": SYNC_ENABLED,
        "s3_prefix": METRICS_S3_PREFIX if SYNC_ENABLED else None,
        "bucket": BUCKET_NAME if SYNC_ENABLED else None,
        "remote_csv": f"{METRICS_S3_PREFIX}metrics.csv" if SYNC_ENABLED else None,
    }
