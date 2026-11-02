"""Создание виртуального окружения и установка зависимостей через Poetry.

Использование:
    python scripts/run_poetry_setup.py

Скрипт:
  1. Проверяет наличие Poetry.
  2. Создаёт виртуальное окружение в корне проекта (.venv).
  3. Устанавливает runtime и dev-зависимости из pyproject.toml/poetry.lock.

Для работы требуется Python 3.12–3.13 (см. pyproject.toml).
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def check_poetry() -> str:
    """Возвращает путь к Poetry, либо завершает работу с ошибкой."""
    poetry = shutil.which("poetry")
    if poetry is None:
        print(
            "[run_poetry_setup] Ошибка: Poetry не найден.\n"
            "Установите Poetry: https://python-poetry.org/docs/#installation\n"
            "Пример: pip install poetry"
        )
        sys.exit(1)
    return poetry


def main() -> int:
    """Запускает poetry install для воспроизводимого окружения."""
    poetry = check_poetry()

    print(f"[run_poetry_setup] Найден Poetry: {poetry}")
    print("[run_poetry_setup] Создаём/обновляем виртуальное окружение...")

    # poetry install с dev-группой и привязкой к poetry.lock
    cmd = [poetry, "install", "--with", "dev", "--no-interaction"]
    print(f"[run_poetry_setup] {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("[run_poetry_setup] Окружение готово.")
        print("[run_poetry_setup] Проверьте: poetry run python --version")
    else:
        print("[run_poetry_setup] Ошибка при установке зависимостей.")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
