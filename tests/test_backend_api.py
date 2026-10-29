"""Живые HTTP-тесты задеплоенного backend (Yandex Serverless Container).

Нужна сеть. Пропускаются автоматически, если backend недоступен (чтобы не ронять
локальный прогон без сети): обёрнуто в try/except при первом обращении.

Запуск только этих тестов:
    python -m pytest tests/ -m api -q
"""

import os
import time

import pytest
import requests

pytestmark = pytest.mark.api


def _feature_vector() -> dict:
    """Строит валидный вектор признаков: все нули, кроме нескольких единичек,
    чтобы предсказание было осмысленным."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "backend",
        "data",
        "feature_names.txt",
    )
    names = []
    with open(path, encoding="utf-8") as f:
        names = [ln.strip() for ln in f if ln.strip()]
    vec = {n: 0 for n in names}
    # Сигналы: 4 комнаты, безопасность, white box, дети есть, автомобиль есть.
    for n in names:
        if "квартира_планировка" in n and "_4_комн" in n:
            vec[n] = 1
        if "приоритеты_безопасность" in n:
            vec[n] = 1
        if "отделка_white_box" in n:
            vec[n] = 1
        if "есть_ли_дети_Есть" in n:
            vec[n] = 1
        if "наличие_автомобиля_Есть" in n:
            vec[n] = 1
    return vec


@pytest.fixture(scope="module")
def live(backend_url):
    """Проверяет доступность backend; если недоступен — все api-тесты пропускаются."""
    try:
        r = requests.get(f"{backend_url}/health", timeout=60)
        r.raise_for_status()
    except Exception as exc:
        pytest.skip(f"Backend недоступен ({backend_url}): {exc}")
    return backend_url


def test_health_ok(live):
    r = requests.get(f"{live}/health", timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("model_loaded") is True
    assert data.get("explainer_loaded") is True


def test_predict_returns_settlement(live):
    r = requests.post(
        f"{live}/predict", json={"features": _feature_vector(), "explicit_factors": []}, timeout=60
    )
    assert r.status_code == 200
    data = r.json()
    assert "klass" in data and isinstance(data["klass"], int)
    assert data.get("settlement") in (
        "Kaskad_Park",
        "Akademia_Park",
        "Fedoskino_Park",
        "Park_Aprel",
    )
    assert isinstance(data.get("top_factors"), list) and len(data["top_factors"]) > 0


def test_metrics_endpoint(live):
    r = requests.get(f"{live}/metrics", timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert "s3_backup" in data


def test_generate_returns_video_url(live):
    """Полный конвейер генерации. Медленный (холодный старт ~10-20с) — поэтому
    отдельным тестом с увеличенным таймаутом."""
    t = time.time()
    r = requests.post(
        f"{live}/generate/",
        json={"features": _feature_vector(), "explicit_factors": [], "tracked": False},
        timeout=180,
    )
    dt = time.time() - t
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    data = r.json()
    assert "video_url" in data and data["video_url"].startswith("http")
    assert "ranked_factors" in data and isinstance(data["ranked_factors"], list)
    print(f"\n  /generate/ занял {dt:.1f} сек")


def test_generate_invalid_payload(live):
    """Невалидный payload — backend должен ответить 4xx/5xx, но не зависнуть."""
    r = requests.post(f"{live}/generate/", json={"features": "не словарь"}, timeout=60)
    # FastAPI/pydantic вернёт 422; если дошло до обработки — 500. Важно: не 200 с мусором.
    assert r.status_code in (422, 500)
