"""Этап 4 — Model registry: версии артефактов модели.

Простой файловый реестр::

    model/
    ├── versions/                  # версии кандидатов: model_vYYYYMMDD.joblib
    │   ├── model_v20260101.joblib
    │   └── ...
    ├── active_model.txt           # указатель активной версии (имя файла)
    └── global_best_model.joblib   # активная версия (копия/ссылка вне версий)

Контур model_update.promote_candidate() записывает новую версию сюда и
переключает указатель; production MODEL_PATH остаётся неизменным — окружение
(Docker-образ) забирает артефакт по указателю при следующем деплое.
"""

import os

from pipeline.config import BACKEND_ROOT

VERSIONS_DIRNAME = "versions"
ACTIVE_POINTER_FILENAME = "active_model.txt"
DEFAULT_MODEL_FILENAME = "global_best_model.joblib"

_MODEL_DIR = os.path.join(BACKEND_ROOT, "model")


def versions_dir() -> str:
    return os.path.join(_MODEL_DIR, VERSIONS_DIRNAME)


def list_versions() -> list[str]:
    """Имена зарегистрированных версий (model_v*.joblib), по алфавиту."""
    d = versions_dir()
    if not os.path.isdir(d):
        return []
    return sorted(fn for fn in os.listdir(d) if fn.endswith(".joblib"))


def active_version() -> str | None:
    """Имя активной версии (содержимое active_model.txt), если указатель задан."""
    p = os.path.join(_MODEL_DIR, ACTIVE_POINTER_FILENAME)
    try:
        with open(p, encoding="utf-8") as f:
            name = f.read().strip()
        return name or None
    except OSError:
        return None


def set_active_version(name: str) -> str:
    """Переключает указатель активной версии. Возвращает путь к артефакту."""
    if not name.endswith(".joblib") or not os.path.exists(os.path.join(versions_dir(), name)):
        raise FileNotFoundError(f"Version not registered: {name}")
    with open(os.path.join(_MODEL_DIR, ACTIVE_POINTER_FILENAME), "w", encoding="utf-8") as f:
        f.write(name + "\n")
    return os.path.join(versions_dir(), name)


def default_model_path() -> str:
    return os.path.join(_MODEL_DIR, DEFAULT_MODEL_FILENAME)
