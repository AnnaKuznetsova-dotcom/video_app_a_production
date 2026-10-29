"""Тесты UTM-хелперов frontend и бизнес-метрик по вариантам сценария
(удержание 3с, досмотры 25/50/75/100, CTR рекламной ссылки, заявки,
стоимость заявки/просмотра) на синтетических CSV."""

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(_ROOT, "frontend"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class _FakeSS:
    """Минимальная замена st.session_state для юнит-тестов UTM-хелперов."""

    def __init__(self, data=None):
        self._d = dict(data or {})

    def __contains__(self, key):
        return key in self._d

    def __getitem__(self, key):
        return self._d[key]

    def __setitem__(self, key, value):
        self._d[key] = value

    def get(self, key, default=None):
        return self._d.get(key, default)


@pytest.fixture(scope="module")
def app():
    import app as _app  # noqa: F401

    return _app


# ---------------------------------------------------------------------------
# UTM: помогает и восстанавливает утилиты при отсутствии рантайма Streamlit.
# ---------------------------------------------------------------------------
def test_utm_helpers_survive_without_runtime(app, monkeypatch):
    monkeypatch.setattr(app.st, "session_state", _FakeSS())
    assert app.capture_utm() == {}
    assert app.utm_query() == ""
    assert app.utm_extra() == ""
    assert app.with_utm("https://kaskad.ru/") == "https://kaskad.ru/"


def test_utm_helpers_attach_known_keys(app, monkeypatch):
    monkeypatch.setattr(
        app.st,
        "session_state",
        _FakeSS(
            {
                "utm": {
                    "utm_source": "ya_direct",
                    "utm_medium": "cpc",
                    "utm_campaign": "kaskad",
                    "utm_term": "kottedzh",
                    "utm_content": "v1",
                }
            }
        ),
    )
    assert app.capture_utm()["utm_source"] == "ya_direct"
    assert "utm_medium=cpc" in app.utm_query()
    url = app.with_utm("https://kaskad.ru/")
    assert (
        url
        == "https://kaskad.ru/?utm_source=ya_direct&utm_medium=cpc&utm_campaign=kaskad&utm_term=kottedzh&utm_content=v1"
    )
    # URL уже с query — добавляем через &
    url2 = app.with_utm("https://kaskad.ru/?x=1")
    assert url2.startswith("https://kaskad.ru/?x=1&utm_source=ya_direct")
    # Переопределение (utm_content=вариант) и URL-кодирование кириллицы.
    url3 = app.with_utm("https://kaskad.ru/", {"utm_content": "1_базовый_Akademia_Park"})
    assert "utm_content=1_%D0%B1%D0%B0%D0%B7%D0%BE%D0%B2%D1%8B%D0%B9_Akademia_Park" in url3
    assert "; utm_source=ya_direct" in app.utm_extra()


def test_param_str_list_returns_first(app):
    assert app._param_str(["a", "b"]) == "a"
    assert app._param_str(("x", "y")) == "x"


# ---------------------------------------------------------------------------
# Бизнес-метрики по вариантам (аналитика на синтетических CSV).
# ---------------------------------------------------------------------------
def _seed_analytics(tmp_path):
    events = str(tmp_path / "events.csv")
    sessions = str(tmp_path / "sessions.csv")
    # Две сессии (разные client_id).
    with open(sessions, "w", encoding="utf-8-sig") as f:
        f.write("ts_iso,client_id,first_touch_ts\n")
        f.write("2026-09-20T10:00:00+00:00,cid_aaa,2026-09-20T10:00:00+00:00\n")
        f.write("2026-09-20T11:00:00+00:00,cid_bbb,2026-09-20T11:00:00+00:00\n")
    # Вариант 1 (из 2 показов: 1 удержание/досмотр/клик, 2 заявки).
    rows = [
        ("cid_aaa", "video_shown", "variant=1_базовый_Akademia_Park; url=http://v.mp4"),
        ("cid_aaa", "video_play", "variant=1_базовый_Akademia_Park; url=http://v.mp4"),
        ("cid_aaa", "video_retention_3s", "variant=1_базовый_Akademia_Park; url=http://v.mp4"),
        ("cid_aaa", "video_watch_25", "variant=1_базовый_Akademia_Park; url=http://v.mp4"),
        ("cid_aaa", "video_watch_50", "variant=1_базовый_Akademia_Park; url=http://v.mp4"),
        ("cid_aaa", "video_watch_75", "variant=1_базовый_Akademia_Park; url=http://v.mp4"),
        ("cid_aaa", "video_watch_100", "variant=1_базовый_Akademia_Park; url=http://v.mp4"),
        ("cid_aaa", "reklama_click", "variant=1_базовый_Akademia_Park; url=http://v.mp4"),
        (
            "cid_aaa",
            "lead_submit",
            "variant=1_базовый_Akademia_Park; name=Иван; phone=+79000000000",
        ),
        (
            "cid_bbb",
            "lead_submit",
            "variant=1_базовый_Akademia_Park; name=Пётр; phone=+79000000001",
        ),
        (
            "cid_bbb",
            "video_shown",
            "variant=1_базовый_Akademia_Park; url=http://v.mp4",
        ),  # 2-й показ без просмотра
        ("cid_bbb", "preview_click", "variant=1_базовый_Akademia_Park"),
    ]
    # Вариант 2 (1 показ, 0 заявок).
    rows.append(("cid_bbb", "video_shown", "variant=2_базовый_Kaskad; url=http://v2.mp4"))
    with open(events, "w", encoding="utf-8-sig") as f:
        f.write("ts_iso,client_id,event_type,extra\n")
        ts = 1
        for cid, ev, extra in rows:
            f.write(f"2026-09-20T10:00:{ts:02d}+00:00,{cid},{ev},{extra}\n")
            ts += 1
    return events, sessions


@pytest.fixture()
def biz(monkeypatch, tmp_path):
    import analytics as _an  # noqa: WPS433

    events, sessions = _seed_analytics(tmp_path)
    monkeypatch.setattr(_an, "EVENTS_CSV", events)
    monkeypatch.setattr(_an, "SESSIONS_CSV", sessions)
    monkeypatch.setenv("CAMPAIGN_SPEND_USD", "100")
    return _an


def test_business_summary_overall(biz):
    s = biz.business_summary()
    assert s["sessions"] == 2
    assert s["assigned_views"] == 3  # всего показов ролика
    assert s["leads"] == 2
    assert s["retention_3s_pct"] == pytest.approx(round(100.0 * 1 / 3, 2))
    assert s["watch_50_pct"] == pytest.approx(round(100.0 * 1 / 3, 2))
    assert s["cost_per_lead_usd"] == 50.0
    assert s["cost_per_assigned_view_usd"] == pytest.approx(round(100.0 / 3, 2))


def test_business_summary_per_variant(biz):
    variants = biz.business_summary()["variants"]
    assert set(variants) == {"1_базовый_Akademia_Park", "2_базовый_Kaskad"}
    v1 = variants["1_базовый_Akademia_Park"]
    assert v1["assigned_views"] == 2
    assert v1["video_plays"] == 1
    assert v1["reklama_clicks"] == 1
    assert v1["leads"] == 2
    assert v1["retention_3s_pct"] == 50.0
    assert v1["watch_100_pct"] == 50.0
    assert v1["ctr_reklama_pct"] == 50.0
    assert v1["cost_per_lead_usd"] == 50.0
    v2 = variants["2_базовый_Kaskad"]
    assert v2["assigned_views"] == 1
    assert v2["video_plays"] == 0
    assert v2["leads"] == 0
    assert v2["cost_per_lead_usd"] is None


def test_log_video_play_writes_variant(biz, tmp_path):
    biz.log_video_play("http://vv.mp4", variant="3_базовый_Fedoskino", utm="utm_source=t")
    assert biz._count_events("video_play", "3_базовый_Fedoskino") == 1
    assert biz._count_events("video_play", "2_базовый_Kaskad") == 0
