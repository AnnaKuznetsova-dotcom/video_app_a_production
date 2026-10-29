"""Общие фикстуры и настройки pytest для проекта KASKAD video-app.

Тесты разделены на две группы:
  - unit:  быстрые проверки чистых функций (без сети, без S3, без моделей).
  - api:   живые HTTP-проверки задеплоенного backend (нужна сеть).

Запуск всех:            python -m pytest tests/ -q
Только unit:            python -m pytest tests/ -q -m "not api"
Только api:             python -m pytest tests/ -q -m api
"""

import os
import sys

import pytest

# Корень проекта, чтобы можно было импортировать frontend/app.py и tools/*.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "frontend"))
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))


def pytest_addoption(parser):
    parser.addoption(
        "--backend-url",
        action="store",
        default=os.getenv("BACKEND_URL", "https://bbaev0p5a3rkd0ps3d4t.containers.yandexcloud.net"),
        help="Базовый URL задеплоенного бэкенда для api-тестов.",
    )


@pytest.fixture(scope="session")
def backend_url(request) -> str:
    return request.config.getoption("--backend-url").rstrip("/")
