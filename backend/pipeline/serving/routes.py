"""HTTP-эндпоинты Video API (вариант A · фиксированный ролик).

Все маршруты регистрируются функцией register_routes(app), которую
вызывает тонкая точка входа backend/main.py.

Эндпоинты:
    GET  /health          — проверка живости контейнера и наличия модели.
    POST /predict         — предсказание класса посёлка.
    POST /generate/       — предсказание + ссылка на фиксированный ролик.
    GET  /metrics         — сводка технических метрик.
    POST /admin/reset_metrics — полный сброс метрик (по токену).
"""

import os
import time
import uuid
from urllib.parse import quote

import pipeline.metrics_tracker as metrics_mod
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pipeline.config import (
    BUCKET_NAME,
    FIXED_VIDEO_BY_SETTLEMENT,
    MEDIA_DIR,
    S3_ENDPOINT,
    VIDEO_S3_ROOT,
    s3_client,
)
from pipeline.data_preprocessing import load_feature_frame
from pipeline.model_inference import (
    MODEL_LOAD_MS,
    is_model_ready,
    next_inference_no,
    predict_settlement,
)
from pydantic import BaseModel

router = APIRouter()


class FeatureVectorPayload(BaseModel):
    """Полный вектор признаков покупателя (все колонки модели)."""

    features: dict
    # опционально: false — не писать этот вызов в метрики (для тестов и отладки)
    tracked: bool = True


class PredictResponse(BaseModel):
    klass: int
    settlement: str
    variant: str


def _variant_id(klass: int, settlement: str) -> str:
    """Идентификатор версии сценария: № класса + «базовый» + название посёлка."""
    return f"{klass}_базовый_{settlement}"


def _fixed_media_url(settlement: str, request: Request) -> str:
    """URL фиксированного ролика посёлка: публичная ссылка на объект в S3 (production)
    или локальная раздача /media/<файл> (режим отладки без S3)."""
    media_name = FIXED_VIDEO_BY_SETTLEMENT.get(settlement)
    if not media_name:
        raise HTTPException(status_code=404, detail=f"Fixed media not mapped for '{settlement}'.")
    if s3_client is not None:
        return f"{S3_ENDPOINT.rstrip('/')}/{BUCKET_NAME}/{VIDEO_S3_ROOT}/{quote(media_name)}"
    media_path = os.path.join(MEDIA_DIR, media_name)
    if not os.path.exists(media_path):
        raise HTTPException(status_code=404, detail=f"Fixed media not found '{settlement}'.")
    return f"{request.base_url}media/{quote(media_name)}"


@router.get("/health")
def health():
    ok = is_model_ready()
    return {
        "status": "ok" if ok else "degraded",
        "mode": "fixed_media_control",
        "media_storage": "s3" if s3_client is not None else "local",
        "video_s3_root": VIDEO_S3_ROOT,
        "model_loaded": ok,
        "bucket": BUCKET_NAME,
        "media_files": sorted(os.listdir(MEDIA_DIR)) if os.path.isdir(MEDIA_DIR) else [],
    }


@router.post("/predict", response_model=PredictResponse)
def predict(payload: FeatureVectorPayload):
    if not is_model_ready():
        raise HTTPException(status_code=500, detail="Model is not loaded.")
    total_start = time.monotonic()
    is_cold = next_inference_no() == 1
    preprocess_ms = predict_ms = 0
    try:
        _t = time.monotonic()
        frame = load_feature_frame(payload.features)
        preprocess_ms = int((time.monotonic() - _t) * 1000)
        _t = time.monotonic()
        klass, settlement = predict_settlement(frame)
        predict_ms = int((time.monotonic() - _t) * 1000)
        variant = _variant_id(klass, settlement)
        metrics_mod.log_inference(
            endpoint="predict",
            settlement=settlement,
            klass=klass,
            total_ms=int((time.monotonic() - total_start) * 1000),
            preprocess_ms=preprocess_ms,
            predict_ms=predict_ms,
            model_load_ms=MODEL_LOAD_MS if is_cold else 0,
            is_cold=is_cold,
            variant=variant,
            success=True,
            skip_log=not payload.tracked,
        )
        return PredictResponse(klass=klass, settlement=settlement, variant=variant)
    except HTTPException:
        raise
    except Exception as exc:
        metrics_mod.log_inference(
            endpoint="predict",
            total_ms=int((time.monotonic() - total_start) * 1000),
            preprocess_ms=preprocess_ms,
            predict_ms=predict_ms,
            is_cold=is_cold,
            success=False,
            error=str(exc),
            skip_log=not payload.tracked,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics")
def get_metrics():
    """Сводка технических метрик (считается из CSV)."""
    return metrics_mod.summary()


@router.post("/admin/reset_metrics")
def reset_metrics(token: str = ""):
    """Полный сброс метрик (локальные CSV + копии в S3). Требует токен из env
    METRICS_ADMIN_TOKEN; если он не задан — сброс запрещён (отключено)."""
    import hmac

    expected = os.getenv("METRICS_ADMIN_TOKEN", "")
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=403,
            detail="Reset is disabled: METRICS_ADMIN_TOKEN not set or wrong token.",
        )
    return metrics_mod.reset_metrics()


@router.post("/generate/")
async def generate_video(payload: FeatureVectorPayload, request: Request):
    if not is_model_ready():
        raise HTTPException(status_code=500, detail="Model is not loaded.")

    job_id = str(uuid.uuid4())
    total_start = time.monotonic()
    is_cold = next_inference_no() == 1
    preprocess_ms = predict_ms = 0
    klass = None
    settlement = ""
    variant = ""
    error_text = None

    try:
        # --- ЭТАП 1: data preprocessing (восстановление полного вектора признаков) ---
        _t0 = time.monotonic()
        feature_frame = load_feature_frame(payload.features)
        preprocess_ms = int((time.monotonic() - _t0) * 1000)
        # --- ЭТАП 2: model inference ---
        _t0 = time.monotonic()
        klass, settlement = predict_settlement(feature_frame)
        predict_ms = int((time.monotonic() - _t0) * 1000)
        variant = _variant_id(klass, settlement)
        print(f"Job {job_id}: class={klass} settlement={settlement} variant={variant}")

        # --- ЭТАП 3 (вариант A): фиксированный ролик предсказанного посёлка.
        # Вместо скачивания фрагментов и склейки отдаём готовый файл. Ролик
        # один и тот же для всех, кто получил этот посёлок — течение контроля.
        video_url = _fixed_media_url(settlement, request)
        total_ms = int((time.monotonic() - total_start) * 1000)
        print(f"Job {job_id}: SUCCESS fixed media url={video_url}")
        return {
            "video_url": video_url,
            "job_id": job_id,
            "variant": variant,
            "settlement": settlement,
            "klass": klass,
            "audio_status": "fixed_media_control",
            "is_cold": is_cold,
            "stage_timing_ms": {
                "preprocess": preprocess_ms,
                "predict": predict_ms,
                "model_load": MODEL_LOAD_MS if is_cold else 0,
                "total": total_ms,
            },
        }

    except HTTPException as exc:
        error_text = (
            f"{getattr(exc, 'status_code', '?')}: {exc.detail if hasattr(exc, 'detail') else exc}"
        )
        raise
    except Exception as exc:  # pragma: no cover
        error_text = str(exc)
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Job {job_id}: {exc}") from exc

    finally:
        total_ms = int((time.monotonic() - total_start) * 1000)
        metrics_mod.log_inference(
            endpoint="generate",
            settlement=settlement,
            klass=klass,
            variant=variant,
            fragments_used=1,
            total_ms=total_ms,
            preprocess_ms=preprocess_ms,
            predict_ms=predict_ms,
            model_load_ms=MODEL_LOAD_MS if is_cold else 0,
            is_cold=is_cold,
            success=error_text is None,
            error=error_text,
            skip_log=not payload.tracked,
        )


def register_routes(app: FastAPI) -> None:
    """Регистрирует все эндпоинты и статический монтиж на переданном app."""
    # Раздача готовых роликов посёлка (вариант A). Файлы лежат в backend/media,
    # имена — из FIXED_VIDEO_BY_SETTLEMENT.
    os.makedirs(MEDIA_DIR, exist_ok=True)
    app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

    # На старте восстанавливаем накопленные метрики из S3-бэкапа, чтобы после
    # перезапуска контейнера /metrics не показывал «no metrics yet». Если бэкапа
    # нет либо S3 не настроен — первый локальный запуск, это нормально.
    try:
        metrics_mod.restore_metrics_from_s3()
    except Exception as _exc:
        print(f"[metrics] restore_metrics_from_s3 failed at startup: {_exc}")

    app.include_router(router)
