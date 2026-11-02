"""Запуск линтера Flake8.

Использование:
    python scripts/run_flake8.py

Flake8 проверяет код на ошибки, нарушения PEP8 и цикломатическую сложность
(McCabe). Настройки читаются из pyproject.toml и .flake8 (если есть).
Скрипт возвращает ненулевой код, если найдены замечания.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Запускает Flake8 для всех Python-файлов проекта."""
    cmd = [
        sys.executable,
        "-m",
        "flake8",
        ".",
    ]
    print(f"[run_flake8] {' '.join(cmd)}")
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
