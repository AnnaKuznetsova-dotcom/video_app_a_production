"""Юнит-тесты реестра моделей и model inference.

Проверяем:
  - `pipeline.model_registry` — перечень версий, указатель active, ошибки
    при неизвестной версии;
  - `pipeline.model_inference` — счётчик инференсов (cold/warm),
    предсказание через подменную модель, флаг готовности модели.
"""

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BACKEND = os.path.join(_ROOT, "backend")
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pipeline import model_inference as mi  # noqa: E402
from pipeline import model_registry as reg  # noqa: E402


@pytest.fixture
def registry_dir(tmp_path, monkeypatch):
    """Временный каталог реестра вместо backend/model/."""
    d = tmp_path / "model"
    d.mkdir()
    monkeypatch.setattr(reg, "_MODEL_DIR", str(d))
    return d


class FakeModel:
    """Люстра-модель: всегда возвращает заданный класс."""

    def __init__(self, klass=2):
        self.klass = klass

    def predict(self, frame):
        import numpy as np

        return np.array([self.klass])


# ---------------------------------------------------------------------------
# model_registry
# ---------------------------------------------------------------------------
def _put_version(d, name="model_v20260101.joblib"):
    versions = os.path.join(d, "versions")
    os.makedirs(versions, exist_ok=True)
    path = os.path.join(versions, name)
    with open(path, "wb") as f:
        f.write(b"fake-joblib-bytes")
    return path


def test_list_versions_empty(registry_dir):
    assert reg.list_versions() == []


def test_list_versions_sorted(registry_dir):
    _put_version(registry_dir, "model_v20260102.joblib")
    _put_version(registry_dir, "model_v20260101.joblib")
    assert reg.list_versions() == ["model_v20260101.joblib", "model_v20260102.joblib"]


def test_active_version_default_none(registry_dir):
    assert reg.active_version() is None


def test_set_active_version(registry_dir):
    _put_version(registry_dir, "model_v20260101.joblib")
    path = reg.set_active_version("model_v20260101.joblib")
    assert os.path.exists(path)
    assert reg.active_version() == "model_v20260101.joblib"


def test_set_active_unknown_version_raises(registry_dir):
    with pytest.raises(FileNotFoundError):
        reg.set_active_version("model_v_unknown.joblib")


def test_default_model_path(registry_dir):
    assert reg.default_model_path() == os.path.join(str(registry_dir), "global_best_model.joblib")


# ---------------------------------------------------------------------------
# model_inference
# ---------------------------------------------------------------------------
def test_is_model_ready_follows_state(monkeypatch):
    monkeypatch.setattr(mi, "model", None)
    assert mi.is_model_ready() is False
    monkeypatch.setattr(mi, "model", object())
    assert mi.is_model_ready() is True


def test_next_inference_no_increments(monkeypatch):
    monkeypatch.setattr(mi, "_INFERENCE_NO", 0)
    assert mi.next_inference_no() == 1
    assert mi.next_inference_no() == 2


def test_predict_settlement_maps_class(monkeypatch, feature_frame):
    monkeypatch.setattr(mi, "model", FakeModel(klass=2))
    klass, settlement = mi.predict_settlement(feature_frame)
    assert klass == 2
    assert settlement == "Fedoskino_Park"


def test_predict_settlement_unknown_class_falls_back(monkeypatch, feature_frame):
    monkeypatch.setattr(mi, "model", FakeModel(klass=99))
    klass, settlement = mi.predict_settlement(feature_frame)
    assert klass == 99
    assert settlement == "Kaskad_Park"


@pytest.fixture(scope="module")
def feature_frame():
    from pipeline.data_preprocessing import load_feature_frame

    names = [
        "bin_num__квартира_планировка_4_комн",
        "bin_num__приоритеты_безопасность",
        "ord__ранг_площади",
    ]
    return load_feature_frame({n: 1 for n in names})
