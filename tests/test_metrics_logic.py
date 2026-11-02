"""Юнит-тесты логики метрик backend (backend/pipeline/metrics_tracker.py).

Проверяем:
  - парсер CSV с дрейфом схем (легаси 11/12/13/19 полей + актуальная v5 = 15);
  - миграцию заголовка на актуальную схему `_ensure_header`;
  - запись инференса `log_inference` и запись сводки `_write_summary`;
  - публичную сводку `summary()` без падения на синтетическом CSV.

Интерпретируемость (SHAP/DFP/Hit Ratio/Spearman) удалена из проекта —
соответствующие тесты тоже убраны.
"""

import csv
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BACKEND = os.path.join(_ROOT, "backend")
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pipeline.metrics_tracker import (  # noqa: E402
    CSV_HEADER,
    _ensure_header,
    _map_csv_row,
    summary,
)


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    """Подменяет пути метрик на tmp и отключает сеть/S3."""
    from pipeline import metrics_tracker as m

    monkeypatch.setattr(m, "CSV_PATH", str(tmp_path / "metrics.csv"), raising=False)
    monkeypatch.setattr(m, "SUMMARY_CSV_PATH", str(tmp_path / "summary.csv"), raising=False)
    monkeypatch.setattr(m, "SYNC_ENABLED", False)
    monkeypatch.setattr(m, "_restored_once", True)
    return m


# ---------------------------------------------------------------------------
# _map_csv_row — парсер строки с дрейфом схем
# ---------------------------------------------------------------------------
def _legacy_row(n):
    """Легаси-строка (v1=11, v2=12, v3=13, v4=19 полей).
    v1: [base 9, success, error]; v2/v3: + (SHAP-колонки, удалены); v4: + хронометраж."""
    base = [
        "2026-09-03T10:00:00",
        "generate",
        "Park_Aprel",
        "3",
        '"[]"',  # top_factors (легаси)
        "4",
        "1200",
        "2300",
        "3500",
    ]
    if n == 11:  # v1
        return base + ["1", ""]
    if n == 12:  # v2: mismatch, success, error
        row = base + ["[]", "1", ""]
    elif n == 13:  # v3: mismatch, success, error, groups_unique
        row = base + ["[]", "1", "", "1"]
    elif n == 19:  # v4: mismatch, success, error, groups_unique + variant-блок
        row = base + ["[]", "1", "", "1"] + ["backend_variant", "5", "6", "7", "8", "1"]
    else:
        raise ValueError(f"unknown legacy length: {n}")
    return row


def _v5_row():
    return [
        "2026-09-03T10:00:00",
        "generate",
        "Park_Aprel",
        "3",
        "1",
        "0",
        "0",
        "3500",
        "1",
        "",
        "backend_variant",
        "5",
        "6",
        "8",
        "1",
    ]


def test_map_legacy_row_11_fields():
    d = _map_csv_row(_legacy_row(11))
    assert d["success"] == "1"
    assert d["error"] == ""
    assert d["total_ms"] == "3500"


def test_map_legacy_row_12_fields():
    d = _map_csv_row(_legacy_row(12))
    assert d["success"] == "1"
    assert d["error"] == ""


def test_map_legacy_row_19_fields():
    d = _map_csv_row(_legacy_row(19))
    assert d["success"] == "1"
    assert d["variant"] == "backend_variant"
    assert d["preprocess_ms"] == "5"
    assert d["predict_ms"] == "6"
    assert d["model_load_ms"] == "8"
    assert d["is_cold"] == "1"


def test_map_v5_row():
    d = _map_csv_row(_v5_row())
    assert d["success"] == "1"
    assert d["variant"] == "backend_variant"
    assert d["preprocess_ms"] == "5"
    assert d["predict_ms"] == "6"
    assert d["model_load_ms"] == "8"
    assert d["is_cold"] == "1"
    assert "top_factors" not in d


# ---------------------------------------------------------------------------
# Заголовок факт-журнала: актуальная схема без SHAP-колонок
# ---------------------------------------------------------------------------
def test_csv_header_has_no_interpretability_columns():
    assert "shap_mismatch_groups" not in CSV_HEADER
    assert "groups_unique" not in CSV_HEADER
    assert "top_factors" not in CSV_HEADER
    assert "shap_ms" not in CSV_HEADER


def test_header_migration(tracker):
    """Старый файл (легаси-шапка) перезаписывается в актуальный формат."""
    old_header = [
        "ts_iso",
        "endpoint",
        "settlement",
        "klass",
        "top_factors",
        "fragments_used",
        "download_ms",
        "render_ms",
        "total_ms",
        "shap_mismatch_groups",
        "success",
        "error",
    ]
    with open(tracker.CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(old_header)
        writer.writerow(_legacy_row(12))
    _ensure_header()
    with open(tracker.CSV_PATH, encoding="utf-8-sig", newline="") as f:
        first = f.readline().strip()
        rows = list(csv.reader(f))
    assert first == ",".join(CSV_HEADER)
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# log_inference + сводка
# ---------------------------------------------------------------------------
def test_log_inference_writes_v5_row(tracker):
    tracker.log_inference(
        endpoint="generate",
        settlement="Park_Aprel",
        klass=3,
        total_ms=3500,
        preprocess_ms=5,
        predict_ms=6,
        model_load_ms=8,
        is_cold=True,
        variant="backend_variant",
    )
    rows = tracker._load_rows()
    assert len(rows) == 1
    assert rows[0]["success"] == "1"
    assert rows[0]["variant"] == "backend_variant"
    assert "top_factors" not in rows[0]


def test_log_inference_skip_log_writes_nothing(tracker):
    tracker.log_inference(endpoint="generate", skip_log=True)
    assert not os.path.exists(tracker.CSV_PATH)


def test_summary_after_inference(tracker):
    tracker.log_inference(
        endpoint="generate",
        settlement="Kaskad_Park",
        klass=0,
        total_ms=4000,
        predict_ms=9,
        variant="0_базовый_Kaskad_Park",
    )
    result = summary()
    assert result["s3_backup"]["s3_enabled"] is False
    # Метрики предложения/объяснений больше в сводке не встречаются.
    assert "dominant_feature_precision_dfp" not in result
    assert "hit_ratio_top3_factors" not in result
    assert "spearman_rho_shap_vs_watchtime" not in result
    assert result["success"] == "1"
    assert result["latency_ms_avg"] == "4000"


def test_summary_empty(tracker):
    result = summary()
    assert result.get("note") == "no metrics yet"
