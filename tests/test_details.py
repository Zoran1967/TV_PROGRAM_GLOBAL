"""Testovi detalja emisije: dodatna XMLTV polja, vrsta (film/serija), tekst i trajni kes.

Svi XML primeri su IZMISLJENI test podaci, ne pravi rasporedi.
"""

import datetime
import os
import sys
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.database.userdata import UserDatabase, _decode_programmes  # noqa: E402
from app.models.schedule import Programme  # noqa: E402
from app.providers.xmltv import parse_xmltv  # noqa: E402
from app.services.schedule_service import ScheduleEntry  # noqa: E402
from app.strings import t as translate  # noqa: E402
from app.utils.details import build_details  # noqa: E402
from app.utils.programme_kind import (  # noqa: E402
    KIND_FILM,
    KIND_OTHER,
    KIND_SERIES,
    programme_kind,
)

BELGRADE = ZoneInfo("Europe/Belgrade")


def _one(extra, title="Naslov"):
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><tv>'
        '<programme start="20261106200000" stop="20261106215500" channel="x.rs">'
        "<title>%s</title>%s</programme></tv>" % (title, extra)
    ).encode("utf-8")
    return parse_xmltv(xml, "x.rs", BELGRADE).programmes[0]


def _t_sr(key):
    return translate(key, "sr")


def _t_en(key):
    return translate(key, "en")


def _entry(programme=None, description=None, end_minutes=115, title="Naslov"):
    start = datetime.datetime(2026, 11, 6, 20, 0, tzinfo=BELGRADE)
    end = start + datetime.timedelta(minutes=end_minutes) if end_minutes else None
    return ScheduleEntry(
        start, end, title, description,
        programme.category if programme else None, programme=programme)


# ---- parser: dodatna polja -----------------------------------------------------

def test_parser_reads_film_details():
    p = _one(
        "<sub-title>Originalni naslov</sub-title><desc>Opis filma.</desc>"
        "<credits><director>Reditelj Prvi</director><actor>Glumac Jedan</actor>"
        '<actor role="x">Glumica Dva</actor></credits>'
        "<date>2019</date><category>Film</category><category>Drama</category>"
        "<country>SAD</country><rating system=\"x\"><value>16</value></rating>",
        title="Test film",
    )
    assert p.year == 2019 and p.subtitle == "Originalni naslov"
    assert p.directors == ("Reditelj Prvi",) and p.actors == ("Glumac Jedan", "Glumica Dva")
    assert p.genres == ("Film", "Drama") and p.category == "Film"
    assert p.countries == ("SAD",) and p.age_rating == "16"
    assert p.season is None and p.episode is None


def test_parser_without_extra_fields_leaves_them_empty():
    p = _one("")
    assert p.subtitle is None and p.year is None and p.age_rating is None
    assert p.genres == () and p.directors == () and p.actors == () and p.countries == ()
    assert (p.season, p.episode, p.episode_total) == (None, None, None)


@pytest.mark.parametrize("xml, expected", [
    ('<episode-num system="xmltv_ns">1.4.0/1</episode-num>', (2, 5, None)),
    ('<episode-num system="xmltv_ns">1.4/10.</episode-num>', (2, 5, 10)),
    ('<episode-num system="xmltv_ns">.7.</episode-num>', (None, 8, None)),
    ('<episode-num system="xmltv_ns">2..</episode-num>', (3, None, None)),
    ('<episode-num system="onscreen">S03E12</episode-num>', (3, 12, None)),
    ('<episode-num system="onscreen">2x05</episode-num>', (2, 5, None)),
    ('<episode-num system="onscreen">Epizoda bez broja</episode-num>', (None, None, None)),
    ('<episode-num system="xmltv_ns">nije broj</episode-num>', (None, None, None)),
    ('<episode-num system="xmltv_ns">...</episode-num>', (None, None, None)),
])
def test_parser_episode_numbers(xml, expected):
    p = _one(xml)
    assert (p.season, p.episode, p.episode_total) == expected


def test_xmltv_ns_wins_over_onscreen():
    p = _one('<episode-num system="onscreen">S09E09</episode-num>'
             '<episode-num system="xmltv_ns">0.1.</episode-num>')
    assert (p.season, p.episode) == (1, 2)


@pytest.mark.parametrize("value, expected", [("2019-05-01", 2019), ("1999", 1999), ("abcd", None),
                                              ("0001", None), ("", None)])
def test_parser_year(value, expected):
    assert _one("<date>%s</date>" % value).year == expected


def test_parser_limits_cast_and_text_length():
    actors = "".join("<actor>Glumac %d</actor>" % n for n in range(40))
    huge = "x" * 5000
    p = _one("<credits>%s</credits><sub-title>%s</sub-title>" % (actors, huge))
    assert len(p.actors) == 12
    assert len(p.subtitle) <= 300


# ---- vrsta emisije ---------------------------------------------------------------

@pytest.mark.parametrize("kwargs, expected", [
    ({"category": "Film"}, KIND_FILM),
    ({"category": "Igrani film"}, KIND_FILM),
    ({"category": "Movie"}, KIND_FILM),
    ({"category": "Dokumentarni film"}, KIND_OTHER),
    ({"category": "Documentary"}, KIND_OTHER),
    ({"category": "Serija"}, KIND_SERIES),
    ({"category": "Domaća serija"}, KIND_SERIES),
    ({"category": "TV Series"}, KIND_SERIES),
    ({"category": "Sapunica"}, KIND_SERIES),
    ({"category": "Informativni"}, KIND_OTHER),
    ({"category": None}, KIND_OTHER),
    ({"season": 1}, KIND_SERIES),
    ({"episode": 3, "category": "Film"}, KIND_SERIES),
    ({"category": "Zabava", "genres": ("Zabava", "Film")}, KIND_FILM),
])
def test_programme_kind(kwargs, expected):
    assert programme_kind(Programme("N", 1, None, **kwargs)) == expected


def test_title_alone_never_decides_the_kind():
    assert programme_kind(Programme("Film o serijama", 1)) == KIND_OTHER
    assert programme_kind(None) == KIND_OTHER


# ---- tekst detalja ---------------------------------------------------------------

def test_film_details_text():
    p = Programme("Test film", 0, 0, "Opis.", "Film", year=2019, age_rating="16",
                  genres=("Film", "Drama"), countries=("SAD",), directors=("Reditelj Prvi",),
                  actors=("Glumac Jedan", "Glumica Dva"))
    title, kind, text = build_details(_t_sr, _entry(p, "Opis."), "20:00-21:55", "RTS 1")
    assert title == "Naslov" and kind == "FILM"
    lines = text.split("\n")
    assert lines[0] == "FILM · 2019 · 1 h 55 min · uzrast 16"
    assert "Emitovanje: 20:00-21:55 · RTS 1" in lines
    assert "Žanr: Film, Drama" in lines
    assert "Režija: Reditelj Prvi" in lines
    assert "Uloge: Glumac Jedan, Glumica Dva" in lines
    assert "Zemlja: SAD" in lines
    assert lines[-1] == "Opis."


def test_series_details_text():
    p = Programme("Serija", 0, 0, "Opis epizode.", "Serija", subtitle="Povratak",
                  season=2, episode=5, episode_total=10, year=2021)
    _, kind, text = build_details(_t_sr, _entry(p, "Opis epizode.", end_minutes=45), "20:00-20:45")
    lines = text.split("\n")
    assert kind == "SERIJA"
    assert lines[0] == "SERIJA · 45 min"
    assert lines[1] == "Sezona 2, epizoda 5 (od 10)"
    assert lines[2] == "Naslov epizode: Povratak"
    assert "Godina: 2021" in lines
    assert not any(line.startswith("Režija") for line in lines)


def test_series_without_season_and_english_text():
    p = Programme("Serial", 0, 0, None, "Series", episode=7)
    _, kind, text = build_details(_t_en, _entry(p, None, end_minutes=60), "20:00-21:00")
    lines = text.split("\n")
    assert kind == "SERIES" and lines[0] == "SERIES · 1 h"
    assert lines[1] == "Episode 7"
    assert lines[-1] == "The source does not provide a description for this programme."


def test_other_programme_and_missing_data_show_no_invented_fields():
    p = Programme("Dnevnik", 0, 0, "Vesti dana", "Informativni")
    _, kind, text = build_details(_t_sr, _entry(p, "Vesti dana", end_minutes=30), "20:00-20:30")
    lines = text.split("\n")
    assert kind == "EMISIJA" and lines[0] == "EMISIJA · 30 min"
    assert "Žanr: Informativni" in lines
    assert not any(l.startswith(("Režija", "Uloge", "Zemlja", "Godina", "Sezona")) for l in lines)
    # bez kraja nema trajanja, bez izvorne emisije nema dodataka
    _, kind, text = build_details(_t_sr, _entry(None, None, end_minutes=None), "20:00")
    assert text.split("\n")[0] == "EMISIJA"


# ---- trajni kes ---------------------------------------------------------------------

def _db(tmp_path):
    return UserDatabase(str(tmp_path / "user.db"), clock=lambda: 1500)


def test_extra_fields_survive_the_persistent_cache(tmp_path):
    saved = [
        Programme("Serija", 100, 200, "Opis", "Serija", subtitle="Epizoda", season=1, episode=2,
                  episode_total=8, year=2020, age_rating="12", genres=("Serija", "Drama"),
                  countries=("SAD",), directors=("A",), actors=("B", "C")),
        Programme("Dnevnik", 300, None),
    ]
    db = _db(tmp_path)
    db.save_schedule("tvprofil", "rts1.rs", 1000, saved)
    _, loaded = db.load_schedule("tvprofil", "rts1.rs")
    assert loaded == saved


def test_old_cache_without_extra_fields_still_loads():
    old = '[["Dnevnik",100,200,"Vesti","Informativni"],["Film",200,null,null,null]]'
    programmes = _decode_programmes(old)
    assert programmes[0] == Programme("Dnevnik", 100, 200, "Vesti", "Informativni")
    assert programmes[1].genres == () and programmes[1].season is None


@pytest.mark.parametrize("payload", [
    '[["N",1,null,null,null,"nije recnik"]]',
    '[["N",1,null,null,null,{"se":"jedan"}]]',
    '[["N",1,null,null,null,{"ac":"nije lista"}]]',
    '[["N",1,null,null,null,{"ge":[1,2]}]]',
    '[["N",1,null,null,null,{"yr":true}]]',
    '[["N",1,null,null,null,{},"visak"]]',
])
def test_damaged_extra_fields_are_rejected(payload):
    with pytest.raises((ValueError, TypeError)):
        _decode_programmes(payload)
