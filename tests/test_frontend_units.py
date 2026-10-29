"""Юнит-тесты чистых функций frontend (без сети, без Streamlit-рантайма)."""

import json
import os
import sys

import pytest

# Гарантированно добавим frontend/ и tools/ в sys.path (независимо от порядка загрузки conftest).
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(_ROOT, "frontend"), os.path.join(_ROOT, "tools"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="module")
def app():
    import app as _app  # noqa: F401  (положит frontend в sys.path)

    return _app


# ---------------------------------------------------------------------------
# validate_phone — формат российского телефона
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "phone,expected",
    [
        ("+7 (900) 123-45-67", True),
        ("8 900 123-45-67", True),
        ("+79001234567", True),
        ("89001234567", True),
        ("9001234567", True),  # без кода страны
        ("", False),  # пустой
        (None, False),  # None
        ("телефон", False),  # буквы
        ("123", False),  # слишком короткий
        ("+7 123 456-78-90", False),  # нет 9 после кода
        ("1234567890123", False),  # слишком длинный
        ("abc12345678", False),
    ],
)
def test_validate_phone(app, phone, expected):
    assert app.validate_phone(phone) is expected


# ---------------------------------------------------------------------------
# area_to_rank — ранг площади
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "area,expected",
    [
        (20, 1),
        (29.9, 1),
        (30, 2),
        (39.9, 2),
        (40, 3),
        (49.9, 3),
        (50, 4),
        (59.9, 4),
        (60, 5),
        (69.9, 5),
        (70, 6),
        (79.9, 6),
        (80, 7),
        (300, 7),
        (19, 0),
        (0, 0),  # вне диапазона -> 0
        (None, 0),
    ],
)
def test_area_to_rank(app, area, expected):
    assert app.area_to_rank(area) == expected


# ---------------------------------------------------------------------------
# _segment_table — границы сегментов по стандартным длительностям
# ---------------------------------------------------------------------------
def test_segment_table_overall_first(app):
    segs = app._segment_table(["bin_num__отделка_white_box"])
    # Первый сегмент — общий вид 5с
    assert segs[0]["name"] == "общий вид"
    assert segs[0]["start"] == 0
    assert segs[0]["dur"] == 5
    # Второй — отделка (4с), стартует с 5
    assert segs[1]["start"] == 5
    assert segs[1]["dur"] == 4


def test_segment_table_durations_by_category(app):
    segs = app._segment_table(
        [
            "bin_num__отделка_white_box",  # 4
            "few_cat__есть_ли_дети_Есть",  # 4
            "bin_num__приоритеты_безопасность",  # 5
            "bin_num__квартира_планировка_4_комн",  # 5
        ]
    )
    durs = [s["dur"] for s in segs]
    # общий вид(5) + отделка(4) + дети(4) + приоритеты(5) + планировка(5)
    assert durs == [5, 4, 4, 5, 5]
    # границы идут подряд
    assert segs[0]["start"] == 0
    assert segs[1]["start"] == segs[0]["start"] + segs[0]["dur"]
    assert segs[2]["start"] == segs[1]["start"] + segs[1]["dur"]


def test_segment_table_empty_factors(app):
    segs = app._segment_table([])
    assert len(segs) == 1
    assert segs[0]["name"] == "общий вид"


# ---------------------------------------------------------------------------
# compute_spearman (tools/view_metrics.py) — ранжирование по времени просмотра
# ---------------------------------------------------------------------------
def _evt(events):
    return [{"event_type": "video_segment_watch", "extra": json.dumps(e)} for e in events]


def test_spearman_perfect(app):
    import view_metrics as vm

    rows = _evt(
        [
            {"segment_names": ["общий вид", "A", "B", "C"], "watched_per_segment": [5, 5, 3, 1]},
        ]
    )
    rho, cnt = vm.compute_spearman(rows)
    assert cnt == 1
    assert rho == 1.0


def test_spearman_inverse(app):
    import view_metrics as vm

    rows = _evt(
        [
            {"segment_names": ["общий вид", "A", "B", "C"], "watched_per_segment": [5, 1, 3, 5]},
        ]
    )
    rho, cnt = vm.compute_spearman(rows)
    assert cnt == 1
    assert rho == -1.0


def test_spearman_no_data(app):
    import view_metrics as vm

    assert vm.compute_spearman([]) is None
    assert vm.compute_spearman([{"event_type": "video_play", "extra": ""}]) is None


# ---------------------------------------------------------------------------
# Дедупликация клипов по группам (бэкенд): один клип на группу (Task: dups)
# ---------------------------------------------------------------------------
def _group_key_of(name):
    GROUPS = [
        {
            "key": "flat_plan",
            "clip_prefix": "bin_num__квартира_планировка",
            "alt_prefix": "few_cat__количество_комнат",
        },
        {"key": "priorities", "clip_prefix": "bin_num__приоритеты"},
        {"key": "finishing", "clip_prefix": "bin_num__отделка"},
        {"key": "children", "clip_prefix": "few_cat__есть_ли_дети"},
    ]
    for grp in GROUPS:
        cp = grp.get("clip_prefix")
        ap = grp.get("alt_prefix")
        if (cp and name.startswith(cp)) or (ap and name.startswith(ap)):
            return grp["key"]
    return None


def _dedupe(feature_names):
    seen = set()
    out = []
    for name in feature_names:
        g = _group_key_of(name)
        if g is None:
            out.append(name)
            continue
        if g in seen:
            continue
        seen.add(g)
        out.append(name)
    return out


def test_dedupe_same_group_twice():
    # 2 клипа «отделка» + 2 «приоритеты» -> остаётся по одному на группу
    r = _dedupe(
        [
            "bin_num__отделка_white_box",
            "bin_num__отделка_missing",
            "bin_num__приоритеты_безопасность",
            "bin_num__приоритеты_missing",
        ]
    )
    assert len(r) == 2
    assert "bin_num__отделка_white_box" in r
    assert "bin_num__приоритеты_безопасность" in r


def test_dedupe_keeps_first_and_unmapped():
    r = _dedupe(
        [
            "bin_num__квартира_планировка_4_комн",
            "few_cat__количество_комнат_4.0",
            "ORD__РАНГ_ПЛОЩАДИ",
        ]
    )
    assert r == ["bin_num__квартира_планировка_4_комн", "ORD__РАНГ_ПЛОЩАДИ"]


def test_dedupe_distinct_groups_unchanged():
    r = _dedupe(
        [
            "bin_num__квартира_планировка_4_комн",
            "bin_num__приоритеты_безопасность",
            "bin_num__отделка_white_box",
            "few_cat__есть_ли_дети_Есть",
        ]
    )
    assert len(r) == 4
    assert len({_group_key_of(x) for x in r}) == 4
