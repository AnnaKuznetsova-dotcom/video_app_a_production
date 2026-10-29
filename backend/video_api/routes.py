"""
HTTP-эндпоинты Video API (вариант A · фиксированный ролик).

Все маршруты регистрируются функцией register_routes(app), которую
вызывает тонкая точка входа backend/main.py.

Эндпоинты:
    GET  /health          — проверка живости контейнера и наличия моделей.
    POST /predict         — только предсказание класса + топ факторов SHAP.
    POST /generate/       — предсказание + ссылка на фиксированный ролик.
    GET  /metrics         — сводка технических метрик.
    POST /admin/reset_metrics — полный сброс метрик (по токену).
"""

import os
import time
import uuid
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from video_api.config import (
    BUCKET_NAME,
    CLASS_MAP,
    FIXED_VIDEO_BY_SETTLEMENT,
    INVERT_SHAP_ORDER,
    MAX_SHAP_FACTORS,
    MEDIA_DIR,
    S3_ENDPOINT,
    VIDEO_PATH_MAP,
    VIDEO_S3_ROOT,
    s3_client,
)
from video_api.models import MODEL_LOAD_MS, _next_inference_no, explainer, model
from video_api.schemas import FeatureVectorPayload, PredictResponse
from video_api.shap_logic import (
    _dedupe_chosen_groups,
    _factor_report,
    _group_key_of,
    _try_load_feature_frame,
    compute_group_shap,
    compute_shap_top_factors,
    group_label_for_chosen,
)
from video_api.video_logic import _variant_id

import metrics as metrics_mod


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

    @app.get("/health")
    def health():
        ok = model is not None and explainer is not None
        return {
            "status": "ok" if ok else "degraded",
            "mode": "fixed_media_control",
            "media_storage": "s3" if s3_client is not None else "local",
            "video_s3_root": VIDEO_S3_ROOT,
            "model_loaded": model is not None,
            "explainer_loaded": explainer is not None,
            "bucket": BUCKET_NAME,
            "media_files": sorted(os.listdir(MEDIA_DIR)) if os.path.isdir(MEDIA_DIR) else [],
        }

    @app.post("/predict", response_model=PredictResponse)
    def predict(payload: FeatureVectorPayload):
        if model is None or explainer is None:
            raise HTTPException(status_code=500, detail="Models are not loaded.")
        total_start = time.monotonic()
        is_cold = _next_inference_no() == 1
        preprocess_ms = predict_ms = shap_ms = 0
        try:
            _t = time.monotonic()
            frame = _try_load_feature_frame(payload.features)
            preprocess_ms = int((time.monotonic() - _t) * 1000)
            _t = time.monotonic()
            klass = int(model.predict(frame)[0])
            predict_ms = int((time.monotonic() - _t) * 1000)
            settlement = CLASS_MAP.get(klass, "Kaskad_Park")
            variant = _variant_id(klass, settlement)
            _t = time.monotonic()
            top_factors = compute_shap_top_factors(frame)
            shap_ms = int((time.monotonic() - _t) * 1000)
            metrics_mod.log_inference(
                endpoint="predict",
                settlement=settlement,
                klass=klass,
                top_factors=top_factors[:MAX_SHAP_FACTORS],
                total_ms=int((time.monotonic() - total_start) * 1000),
                preprocess_ms=preprocess_ms,
                predict_ms=predict_ms,
                shap_ms=shap_ms,
                model_load_ms=MODEL_LOAD_MS if is_cold else 0,
                is_cold=is_cold,
                variant=variant,
                success=True,
                skip_log=not payload.tracked,
            )
            return PredictResponse(
                klass=klass, settlement=settlement, variant=variant, top_factors=top_factors
            )
        except HTTPException:
            raise
        except Exception as exc:
            metrics_mod.log_inference(
                endpoint="predict",
                total_ms=int((time.monotonic() - total_start) * 1000),
                preprocess_ms=preprocess_ms,
                predict_ms=predict_ms,
                shap_ms=shap_ms,
                is_cold=is_cold,
                success=False,
                error=str(exc),
                skip_log=not payload.tracked,
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/metrics")
    def get_metrics():
        """Сводка технических метрик (считается из CSV)."""
        return metrics_mod.summary()

    @app.post("/admin/reset_metrics")
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

    @app.post("/generate/")
    async def generate_video(payload: FeatureVectorPayload, request: Request):
        if model is None or explainer is None:
            raise HTTPException(status_code=500, detail="Models are not loaded.")

        job_id = str(uuid.uuid4())
        total_start = time.monotonic()
        is_cold = _next_inference_no() == 1
        preprocess_ms = predict_ms = shap_ms = 0
        download_ms = 0
        render_ms = 0
        klass = None
        settlement = ""
        variant = ""
        chosen = []
        ranked_factors = []
        shap_values = []
        shap_mismatch_groups = []
        fragments_used = 0
        error_text = None

        try:
            # --- ЭТАП 0: preprocessing (восстановление полного вектора признаков) ---
            _t0 = time.monotonic()
            feature_frame = _try_load_feature_frame(payload.features)
            preprocess_ms = int((time.monotonic() - _t0) * 1000)
            # --- ЭТАП 1: prediction ---
            _t0 = time.monotonic()
            klass = int(model.predict(feature_frame)[0])
            predict_ms = int((time.monotonic() - _t0) * 1000)
            settlement = CLASS_MAP.get(klass, "Kaskad_Park")
            variant = _variant_id(klass, settlement)
            print(
                f"Job {job_id}: class={klass} settlement={settlement} variant={variant} (fixed media)"
            )

            # --- ЭТАП 2: SHAP-объяснение (группировка по смысловым блокам) ---
            # Логика ответа/graph-данных сохранена КАК В ИСХОДНОЙ ВЕРСИИ; меняется
            # только генерация ролика (ниже). Это позволяет сравнивать A/B/C по
            # единственному измерению — способу сборки видео.
            _t0 = time.monotonic()
            shap_mismatch_groups = []
            if payload.explicit_factors:
                # Обходной путь: клиент сам задал факторы — без группировки.
                sorted_factors = payload.explicit_factors
                chosen_feature_names = [
                    f for f in sorted_factors if VIDEO_PATH_MAP.get(f) is not None
                ]
                group_rows = None
            else:
                # Главный путь: считаем SHAP и ГРУППИРУЕМ по смысловым блокам.
                group_rows = compute_group_shap(feature_frame)
                chosen_feature_names = [
                    gr["chosen_feature"]
                    for gr in group_rows
                    if gr["chosen_feature"] and VIDEO_PATH_MAP.get(gr["chosen_feature"]) is not None
                ][:MAX_SHAP_FACTORS]
                # alert-метрика — где выбор клиента НЕ является max по SHAP
                # внутри своей группы (сигнал качества модели/классификации).
                for gr in group_rows:
                    if not gr["is_max"]:
                        shap_mismatch_groups.append(
                            {
                                "group": gr["key"],
                                "label": gr["label"],
                                "chosen": gr["chosen_feature"],
                                "max": gr["max_feature"],
                                "chosen_shap": round(gr["chosen_shap"], 4),
                                "max_shap": round(gr["max_shap"], 4),
                            }
                        )
                # Для бар-плота на фронте отдаём данные по ГРУППАМ: подпись =
                # группа + выбранный вариант, значение = сумма |SHAP|.
                shap_values = [
                    {"name": group_label_for_chosen(gr), "value": round(float(gr["sum_shap"]), 4)}
                    for gr in group_rows
                ]
                print(f"Job {job_id}: shap_mismatch_groups={shap_mismatch_groups}")

            ranked_factors = chosen_feature_names[:MAX_SHAP_FACTORS]
            if payload.explicit_factors:
                shap_values = [
                    {"name": f, "value": 1.0} for f in chosen_feature_names[:MAX_SHAP_FACTORS]
                ]
            else:
                shap_values = shap_values[:10]
            shap_ms = int((time.monotonic() - _t0) * 1000)

            chosen = _dedupe_chosen_groups(chosen_feature_names[: MAX_SHAP_FACTORS * 2])
            chosen = chosen[:MAX_SHAP_FACTORS]
            if INVERT_SHAP_ORDER:
                chosen = chosen[::-1]  # самый важный — в финал

            # --- ЭТАП ГЕНЕРАЦИИ (вариант A): фиксированный ролик посёлка ---
            # Вместо скачивания фрагментов и склейки отдаём готовый файл. Ролик
            # один и тот же для всех, кто получил этот посёлок — течение контроля.
            media_name = FIXED_VIDEO_BY_SETTLEMENT.get(settlement)
            if not media_name:
                raise HTTPException(
                    status_code=404,
                    detail=f"Fixed media not mapped for settlement '{settlement}'.",
                )
            if s3_client is not None:
                # Production: ролик уже лежит в бакете в корневой папке
                # Kaskad_Video — отдаём прямой публичный URL на объект.
                video_url = (
                    f"{S3_ENDPOINT.rstrip('/')}/{BUCKET_NAME}/"
                    f"{VIDEO_S3_ROOT}/{quote(media_name)}"
                )
            else:
                # Локальный режим (проверка в Streamlit без S3): отдаём файл сами.
                media_path = os.path.join(MEDIA_DIR, media_name)
                if not os.path.exists(media_path):
                    raise HTTPException(
                        status_code=404,
                        detail=f"Fixed media not found for settlement '{settlement}'.",
                    )
                video_url = f"{request.base_url}media/{quote(media_name)}"
            fragments_used = 1
            render_ms = 0
            audio_status = "fixed_media_control"
            total_ms = int((time.monotonic() - total_start) * 1000)
            factor_report = _factor_report(feature_frame, ranked_factors)
            print(f"Job {job_id}: SUCCESS fixed media url={video_url}")
            return {
                "video_url": video_url,
                "job_id": job_id,
                "variant": variant,
                "settlement": settlement,
                "klass": klass,
                "used_factors": chosen,
                "ranked_factors": ranked_factors,
                "shap_values": shap_values,
                "shap_mismatch_groups": shap_mismatch_groups,
                "factor_report": factor_report,
                "audio_status": audio_status,
                "is_cold": is_cold,
                "stage_timing_ms": {
                    "preprocess": preprocess_ms,
                    "predict": predict_ms,
                    "shap": shap_ms,
                    "model_load": MODEL_LOAD_MS if is_cold else 0,
                    "total": total_ms,
                },
            }

        except HTTPException as exc:
            error_text = f"{getattr(exc, 'status_code', '?')}: {exc.detail if hasattr(exc, 'detail') else exc}"
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
                top_factors=ranked_factors,
                fragments_used=fragments_used,
                download_ms=download_ms,
                render_ms=render_ms,
                total_ms=total_ms,
                preprocess_ms=preprocess_ms,
                predict_ms=predict_ms,
                shap_ms=shap_ms,
                model_load_ms=MODEL_LOAD_MS if is_cold else 0,
                is_cold=is_cold,
                shap_mismatch_groups=shap_mismatch_groups,
                groups_unique=len({k for f in chosen if (k := _group_key_of(f)) is not None})
                == len([k for f in chosen if (_group_key_of(f)) is not None]),
                success=error_text is None,
                error=error_text,
                skip_log=not payload.tracked,
            )
