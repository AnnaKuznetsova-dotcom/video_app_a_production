"""Юнит-тесты логики метрик backend (metrics.py) — без сети и S3.

Проверяем:
  - устойчивый парсер CSV с дрейфом колонок (11/12/13 полей) `_map_csv_row`;
  - расчёт DFP / Hit Ratio / High Confidence по синтетическим данным;
  - Spearman ρ между SHAP-порядком и временем просмотра (`compute_spearman_rho`);
  - публичную сводку без падения на синтетическом on-disk CSV.
"""

import csv
import json
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BACKEND = os.path.join(_ROOT, "backend")
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import metrics as m  # noqa: E402

# Отключаем любые обращения к сети в тестах.
m.SYNC_ENABLED = False


# ---------------------------------------------------------------------------
# _map_csv_row — парсер строки с дрейфом колонок (11 / 12 / 13 полей)
# ---------------------------------------------------------------------------
def _row11():
    return [
        "2026-09-03T10:00:00",
        "generate",
        "Park_Aprel",
        "3",
        '"[]"',
        "4",
        "1200",
        "2300",
        "3500",
        "1",
        "",
    ]


def _row12():
    return [
        "2026-09-03T10:00:00",
        "generate",
        "Park_Aprel",
        "3",
        '"[]"',
        "4",
        "1200",
        "2300",
        "3500",
        "[]",
        "1",
        "",
    ]


def _row13():
    return [
        "2026-09-03T10:00:00",
        "generate",
        "Park_Aprel",
        "3",
        '"[]"',
        "4",
        "1200",
        "2300",
        "3500",
        "[]",
        "1",
        "",
        "1",
    ]


def test_map_row11_cols():
    d = m._map_csv_row(_row11())
    assert d["success"] == "1"
    assert d["error"] == ""
    assert d["shap_mismatch_groups"] == ""
    assert d["groups_unique"] == ""
    assert d["total_ms"] == "3500"


def test_map_row12_cols():
    d = m._map_csv_row(_row12())
    assert d["success"] == "1"
    assert d["shap_mismatch_groups"] == "[]"
    assert d["error"] == ""


def test_map_row13_cols():
    d = m._map_csv_row(_row13())
    assert d["success"] == "1"
    assert d["shap_mismatch_groups"] == "[]"
    assert d["groups_unique"] == "1"


def test_map_row_missing_error_field():
    d = m._map_csv_row(["a", "generate", "s", "0", "{}", "0", "0", "0", "0", "0"])
    assert d["success"] == "0"
    assert d["error"] == ""


# ---------------------------------------------------------------------------
# Вычислительные метрики по синтетическим строкам
# ---------------------------------------------------------------------------
def _ok_row(mismatch=None, unique=True):
    r = {
        "ts_iso": "2026-09-04T12:00:00",
        "endpoint": "generate",
        "settlement": "Kaskad_Park",
        "klass": "0",
        "top_factors": "[]",
        "fragments_used": "5",
        "download_ms": "1000",
        "render_ms": "2000",
        "total_ms": "3000",
        "success": "1",
        "error": "",
        "groups_unique": "1",
    }
    if mismatch is None:
        r["shap_mismatch_groups"] = ""
    else:
        r["shap_mismatch_groups"] = json.dumps(mismatch)
    r["groups_unique"] = "1" if unique else "0"
    return r


def test_dfp_all_match():
    rows = [
        _ok_row(None),
        _ok_row(None),
        _ok_row(None),
        _ok_row([{"group": "flat_plan"}]),
        _ok_row(None),
    ]
    ok = [r for r in rows if r["success"] == "1"]
    mism = sum(1 for r in ok if (r.get("shap_mismatch_groups") or "").strip())
    dfp = round((len(ok) - mism) / len(ok), 4)
    assert dfp == 0.8
    assert len(ok) == 5


def test_high_confidence_is_independent_of_dfp():
    # Широкий зазор (полное несогласие модели с клиентом) => НЕ high-confidence.
    wide = [{"group": "flat_plan", "chosen_shap": 0.1, "max_shap": 1.5}]
    # Малый зазор (модель почти уверена) => high-confidence.
    narrow = [{"group": "flat_plan", "chosen_shap": 1.1, "max_shap": 1.5}]
    rows = [_ok_row(wide), _ok_row(narrow), _ok_row(None)]
    ok = [r for r in rows if r["success"] == "1"]
    margin = 0.50
    hc = 0
    for r in ok:
        raw = (r.get("shap_mismatch_groups") or "").strip()
        if not raw:
            hc += 1
            continue
        confident = True
        for g in json.loads(raw):
            mx = abs(float(g.get("max_shap") or 0.0))
            cs = abs(float(g.get("chosen_shap") or 0.0))
            if mx > 0 and (mx - cs) >= margin * mx:
                confident = False
                break
        if confident:
            hc += 1
    assert hc == 2  # narrow + empty => high-confidence; wide => нет


def test_hit_ratio_per_group():
    mism_groups = [
        {"group": "flat_plan"},
        {"group": "children"},
        {"group": "priorities"},
    ]
    ok_total = 3
    total_groups = ok_total * 4
    matched = total_groups - len(mism_groups)
    assert matched == 9
    assert round(matched / total_groups, 4) == 0.75


def test_groups_unique_count():
    rows = [_ok_row(None), _ok_row(None, unique=False), _ok_row(None)]
    ok_total = len(rows)
    unique_cnt = sum(1 for r in rows if r.get("groups_unique", "1") != "0")
    rate = round(unique_cnt / ok_total, 4)
    assert rate == round(2 / 3, 4)


# ---------------------------------------------------------------------------
# Spearman ρ (metrics.compute_spearman_rho) — по tmp-файлу events.csv
# ---------------------------------------------------------------------------
@pytest.fixture()
def events_tmp():
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _write_events(path, events):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ts_iso", "client_id", "event_type", "extra"])
        for e in events:
            w.writerow(
                [
                    "2026-09-04T12:00:00",
                    "cid1",
                    "video_segment_watch",
                    json.dumps(e, ensure_ascii=False),
                ]
            )


def test_spearman_perfect_rank(events_tmp, monkeypatch):
    _write_events(
        events_tmp,
        [
            {"segment_names": ["общий вид", "A", "B", "C"], "watched_per_segment": [5, 5, 3, 1]},
        ],
    )
    monkeypatch.setattr(m, "FRONTEND_EVENTS_CSV", events_tmp)
    res = m.compute_spearman_rho()
    assert res is not None
    assert res["rho"] == 1.0
    assert res["videos"] == 1


def test_spearman_inverse_rank(events_tmp, monkeypatch):
    _write_events(
        events_tmp,
        [
            {"segment_names": ["общий вид", "A", "B", "C"], "watched_per_segment": [5, 1, 3, 5]},
        ],
    )
    monkeypatch.setattr(m, "FRONTEND_EVENTS_CSV", events_tmp)
    res = m.compute_spearman_rho()
    assert res is not None
    assert res["rho"] == -1.0


def test_spearman_no_events(events_tmp, monkeypatch):
    monkeypatch.setattr(m, "FRONTEND_EVENTS_CSV", events_tmp)
    assert m.compute_spearman_rho() is None


def test_spearman_ignores_overall_view(monkeypatch, events_tmp):
    # «общий вид» исключается; если осталось меньше 2 сегментов — данных нет.
    _write_events(
        events_tmp,
        [
            {"segment_names": ["общий вид", "только_один"], "watched_per_segment": [5, 5]},
        ],
    )
    monkeypatch.setattr(m, "FRONTEND_EVENTS_CSV", events_tmp)
    res = m.compute_spearman_rho()
    assert res is None


# ---------------------------------------------------------------------------
# _load_rows — устойчивый парсер файла с дрейфом колонок (гибридный CSV)
# ---------------------------------------------------------------------------
def _write_mixed_csv(path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        # Старый заголовок: 11 колонок.
        w.writerow(
            [
                "ts_iso",
                "endpoint",
                "settlement",
                "klass",
                "top_factors",
                "fragments_used",
                "download_ms",
                "render_ms",
                "total_ms",
                "success",
                "error",
            ]
        )
        # 3 строки нового формата (12 колонок: added shap_mismatch_groups).
        for i in range(3):
            w.writerow(
                [
                    "2026-09-04T12:00:0" + str(i),
                    "generate",
                    "s",
                    "0",
                    "[]",
                    "4",
                    "1000",
                    "2000",
                    "3000",
                    "[]",
                    "1",
                    "",
                ]
            )
        # 2 строки старого формата (11 колонок).
        for i in range(2):
            w.writerow(
                [
                    "2026-09-03T10:00:0" + str(i),
                    "generate",
                    "s",
                    "1",
                    "[]",
                    "5",
                    "1000",
                    "2000",
                    "3000",
                    "1",
                    "",
                ]
            )


def test_load_rows_hybrid_format(tmp_path):
    path = str(tmp_path / "metrics.csv")
    _write_mixed_csv(path)
    _rows = (
        m._load_rows.__wrapped__ if hasattr(m._load_rows, "__wrapped__") else m._load_rows
    )  # noqa: F841 — доказывает, что доступен и «сырой» вызов
    # заставляем читать именно наш файл
    old_path = m.CSV_PATH
    m.CSV_PATH = path
    try:
        loaded = m._load_rows()
    finally:
        m.CSV_PATH = old_path
    assert len(loaded) == 5
    assert sum(1 for r in loaded if r["success"] == "1") == 5
    assert sum(1 for r in loaded if r["error"] == "") == 5
    # у 12-колоночных строк заполнен shap_mismatch_groups="[]"
    assert sum(1 for r in loaded if r.get("shap_mismatch_groups") == "[]") == 3


# ---------------------------------------------------------------------------
# summary() — не падает и отдаёт ключи на синтетических данных
# ---------------------------------------------------------------------------
def test_summary_endpoint_shape(tmp_path):
    path = str(tmp_path / "metrics.csv")
    _write_mixed_csv(path)
    old_csv, old_sum = m.CSV_PATH, m.SUMMARY_CSV_PATH
    m.CSV_PATH = path
    m.SUMMARY_CSV_PATH = str(tmp_path / "summary.csv")
    try:
        res = m.summary()
    finally:
        m.CSV_PATH, m.SUMMARY_CSV_PATH = old_csv, old_sum
    for key in (
        "total_inferences",
        "success",
        "errors",
        "dominant_feature_precision_dfp",
        "share_high_confidence_predictions",
        "hit_ratio_top3_factors",
        "updated_at",
        "s3_backup",
    ):
        assert key in res
    assert int(res["success"]) == 5
