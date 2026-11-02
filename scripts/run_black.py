"""Запуск автоформатирования кода через Black.

Использование:
    python scripts/run_black.py

Black перезаписывает файлы в соответствии с настройками из pyproject.toml
(line-length = 100, target-version = py312). Скрипт возвращает ненулевой код,
если Black не установлен или обнаружил ошибки форматирования.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Запускает Black для всех Python-файлов проекта."""
    cmd = [
        sys.executable,
        "-m",
        "black",
        "--line-length",
        "100",
        ".",
    ]
    print(f"[run_black] {' '.join(cmd)}")
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
