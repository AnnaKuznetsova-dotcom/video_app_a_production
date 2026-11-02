"""Шаг BPMN «Регистрация новой версии» (после бизнес-утверждения).

Что делает популяция:

    1. Копирует кандидат в model_weight/versions/ (имя model_v*.joblib);
    2. Пишет model/baseline_metrics.json (новый baseline);
    3. Переключает активную версию через model_registry.set_active_version;
    4. Обновляет артефакт production (global_best_model.joblib), чтобы Docker-
       образ нового деплоя забрал собой правильную модель.

Отмерший артефакт предыдущей версии остаётся в versions/ для откката.
"""

import json
import os
import shutil

from pipeline.model_registry import (
    _MODEL_DIR,
    ACTIVE_POINTER_FILENAME,
    DEFAULT_MODEL_FILENAME,
    list_versions,
    set_active_version,
)


def promote_candidate(
    candidate_path: str,
    metrics: dict,
    *,
    approved_by: str = "",
) -> dict:
    """Регистрирует кандидата как активную версию. Возвращает отчёт о шаге."""
    if not os.path.exists(candidate_path):
        raise FileNotFoundError(candidate_path)

    name = os.path.basename(candidate_path)
    shutil.copy2(candidate_path, os.path.join(_MODEL_DIR, name))

    with open(os.path.join(_MODEL_DIR, "baseline_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"approved_by": approved_by, **metrics}, f, ensure_ascii=False, indent=2)

    artifact_path = set_active_version(name)

    # Production-артефакт: копия активной версии под каноническим именем.
    production_path = os.path.join(_MODEL_DIR, DEFAULT_MODEL_FILENAME)
    shutil.copy2(candidate_path, production_path)

    return {
        "version": name,
        "registry_pointer": os.path.join(_MODEL_DIR, ACTIVE_POINTER_FILENAME),
        "artifact_path": artifact_path,
        "production_path": production_path,
        "baseline_written": True,
        "versions_registered": list_versions(),
    }
