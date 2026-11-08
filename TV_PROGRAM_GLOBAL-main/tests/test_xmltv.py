"""Testovi XMLTV parsera. Svi XML primeri su IZMISLJENI test podaci, ne pravi rasporedi."""

import datetime
import os
import sys
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.providers.errors import (  # noqa: E402
    EmptyResponseError,
    EmptyScheduleError,
    ParseError,
    ZoneUnavailableError,
)
from app.providers.xmltv import load_zone, parse_time, parse_xmltv  # noqa: E402

BELGRADE = ZoneInfo("Europe/Belgrade")
UTC = datetime.timezone.utc


def utc(year, month, day, hour=0, minute=0, second=0):
    return int(datetime.datetime(year, month, day, hour, minute, second, tzinfo=UTC).timestamp())


def programme(start, stop=None, title="Test emisija", channel="test.sr", extra=""):
    stop_attr = ' stop="%s"' % stop if stop else ""
    title_xml = '<title lang="sr">%s</title>' % title if title is not None else ""
    return '<programme start="%s"%s channel="%s">%s%s</programme>' % (
        start, stop_attr, channel, title_xml, extra)


def tv(*items, doctype=True):
    head = '<?xml version="1.0" encoding="UTF-8"?>\n'
    if doctype:
        head += '<!DOCTYPE tv SYSTEM "xmltv.dtd">\n'
    return (head + "<tv>" + "".join(items) + "</tv>").encode("utf-8")


# ---- vreme ---------------------------------------------------------------

def test_time_with_offset_is_exact_utc():
    assert parse_time("20261106193000 +0100") == (utc(2026, 11, 6, 18, 30), False)
    assert parse_time("20261106193000 -0500") == (utc(2026, 11, 7, 0, 30), False)
    assert parse_time("20261106193000+0100") == (utc(2026, 11, 6, 18, 30), False)
    assert parse_time("20261106193000 Z") == (utc(2026, 11, 6, 19, 30), False)


def test_floating_time_uses_zone():
    value, floating = parse_time("20261106193000", BELGRADE)
    assert floating and value == utc(2026, 11, 6, 18, 30)  # zimsko vreme, +01:00
    value, _ = parse_time("20260715193000", BELGRADE)
    assert value == utc(2026, 7, 15, 17, 30)  # letnje vreme, +02:00


def test_floating_time_without_zone_is_an_error():
    with pytest.raises(ZoneUnavailableError):
        parse_time("20261106193000", None)


@pytest.mark.parametrize("text", ["", None, "abc", "2026-11-06 19:30", "20261340193000",
                                  "20260230120000", "20261106256000"])
def test_bad_time_formats(text):
    with pytest.raises(ValueError):
        parse_time(text, BELGRADE)


def test_short_time_forms():
    assert parse_time("202611061930", BELGRADE)[0] == utc(2026, 11, 6, 18, 30)
    assert parse_time("20261106", BELGRADE)[0] == utc(2026, 11, 5, 23, 0)


def test_unknown_zone_is_reported():
    with pytest.raises(ZoneUnavailableError):
        load_zone("Nema/Takve_Zone")
    with pytest.raises(ZoneUnavailableError):
        load_zone(None)


# ---- osnovno citanje -------------------------------------------------------

def test_parses_basic_schedule_with_all_fields():
    data = tv(
        programme("20261106180000", "20261106190000", "Dnevnik", extra=(
            '<desc lang="sr">Vesti  dana\n  i vreme</desc><category lang="sr">Informativni</category>')),
        programme("20261106190000", "20261106200000", "Film"),
    )
    result = parse_xmltv(data, "test.sr", BELGRADE)
    assert [p.title for p in result.programmes] == ["Dnevnik", "Film"]
    first = result.programmes[0]
    assert first.start_utc == utc(2026, 11, 6, 17, 0)
    assert first.end_utc == utc(2026, 11, 6, 18, 0)
    assert first.description == "Vesti dana i vreme"
    assert first.category == "Informativni"
    assert result.programmes[1].description is None and result.programmes[1].category is None
    assert result.stats.kept == 2 and result.stats.total == 2


def test_doctype_with_external_dtd_is_accepted():
    assert parse_xmltv(tv(programme("20261106180000+0100"), doctype=True), "test.sr").stats.kept == 1


def test_missing_stop_gives_no_end_time():
    result = parse_xmltv(tv(programme("20261106180000", None, "Bez kraja")), "test.sr", BELGRADE)
    assert result.programmes[0].end_utc is None


def test_stop_before_start_is_dropped():
    result = parse_xmltv(tv(programme("20261106180000", "20261106170000", "Cudno")), "test.sr", BELGRADE)
    assert result.programmes[0].end_utc is None


def test_programme_without_title_is_skipped():
    data = tv(programme("20261106180000", title=None), programme("20261106190000", title="Ima naslov"),
              programme("20261106200000", title="   "))
    result = parse_xmltv(data, "test.sr", BELGRADE)
    assert [p.title for p in result.programmes] == ["Ima naslov"]
    assert result.stats.no_title == 2


def test_bad_time_programme_is_skipped_but_rest_is_kept():
    data = tv(programme("nije_vreme", title="Lose"), programme("20261106190000", title="Dobro"))
    result = parse_xmltv(data, "test.sr", BELGRADE)
    assert [p.title for p in result.programmes] == ["Dobro"]
    assert result.stats.bad_time == 1


def test_other_channels_are_ignored_case_insensitively():
    data = tv(programme("20261106180000", title="Moja", channel="TEST.SR"),
              programme("20261106190000", title="Tudja", channel="drugi.sr"))
    result = parse_xmltv(data, "test.sr", BELGRADE)
    assert [p.title for p in result.programmes] == ["Moja"]
    assert result.stats.other_channel == 1


def test_duplicates_are_removed_and_order_is_fixed():
    data = tv(programme("20261106190000", title="Druga"), programme("20261106180000", title="Prva"),
              programme("20261106180000", title="Prva"))
    result = parse_xmltv(data, "test.sr", BELGRADE)
    assert [p.title for p in result.programmes] == ["Prva", "Druga"]
    assert result.stats.duplicates == 1


def test_non_ascii_titles_and_windows_1250_encoding():
    xml = ('<?xml version="1.0" encoding="windows-1250"?><tv>'
           + programme("20261106180000", title="Čaršija šuma đak žaba")
           + "</tv>").encode("windows-1250")
    result = parse_xmltv(xml, "test.sr", BELGRADE)
    assert result.programmes[0].title == "Čaršija šuma đak žaba"


# ---- greske ------------------------------------------------------------------

def test_empty_and_whitespace_input():
    for data in (b"", b"   \n", None):
        with pytest.raises(EmptyResponseError):
            parse_xmltv(data, "test.sr", BELGRADE)


@pytest.mark.parametrize("data", [
    b"<html><body>Greska 500</body></html>",
    b"ovo uopste nije xml",
    b"<tv><programme start='x'>",
    b'<?xml version="1.0"?><rss><channel/></rss>',
    b"\x00\x01\x02\xff\xfe",
])
def test_garbage_is_a_parse_error(data):
    with pytest.raises(ParseError):
        parse_xmltv(data, "test.sr", BELGRADE)


def test_entity_definitions_are_rejected():
    bomb = (b'<?xml version="1.0"?><!DOCTYPE tv [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
            b"<tv><programme start='20261106180000' channel='test.sr'><title>&b;</title></programme></tv>")
    with pytest.raises(ParseError):
        parse_xmltv(bomb, "test.sr", BELGRADE)


def test_valid_file_without_programmes_for_channel():
    with pytest.raises(EmptyScheduleError):
        parse_xmltv(tv(), "test.sr", BELGRADE)
    with pytest.raises(EmptyScheduleError):
        parse_xmltv(tv(programme("20261106180000", channel="drugi.sr")), "test.sr", BELGRADE)


def test_floating_times_without_zone_raise():
    with pytest.raises(ZoneUnavailableError):
        parse_xmltv(tv(programme("20261106180000")), "test.sr", None)


def test_times_with_offsets_need_no_zone():
    result = parse_xmltv(tv(programme("20261106180000 +0100")), "test.sr", None)
    assert result.programmes[0].start_utc == utc(2026, 11, 6, 17, 0)


# ---- prelazak na letnje/zimsko racunanje vremena -------------------------------

def test_autumn_clock_change_repeated_hour_stays_in_order():
    # 25.10.2026. u 03:00 letnje vreme se vraca na 02:00 zimsko: sat 02:xx se desava dvaput.
    times = ["20261025013000", "20261025020000", "20261025023000",
             "20261025020000", "20261025023000", "20261025030000"]
    data = tv(*[programme(t, title="E%d" % i) for i, t in enumerate(times)])
    result = parse_xmltv(data, "test.sr", BELGRADE)
    starts = [p.start_utc for p in result.programmes]
    assert [p.title for p in result.programmes] == ["E0", "E1", "E2", "E3", "E4", "E5"]
    assert starts == [
        utc(2026, 10, 24, 23, 30),  # 01:30 CEST
        utc(2026, 10, 25, 0, 0),    # 02:00 CEST (prvi put)
        utc(2026, 10, 25, 0, 30),   # 02:30 CEST
        utc(2026, 10, 25, 1, 0),    # 02:00 CET (drugi put)
        utc(2026, 10, 25, 1, 30),   # 02:30 CET
        utc(2026, 10, 25, 2, 0),    # 03:00 CET
    ]


def test_spring_clock_change_skips_the_missing_hour():
    # 28.03.2027. u 02:00 zimsko preskace na 03:00 letnje: lokalnog 02:xx nema.
    times = ["20270328013000", "20270328030000", "20270328040000"]
    data = tv(*[programme(t, title="P%d" % i) for i, t in enumerate(times)])
    result = parse_xmltv(data, "test.sr", BELGRADE)
    assert [p.start_utc for p in result.programmes] == [
        utc(2027, 3, 28, 0, 30),  # 01:30 CET
        utc(2027, 3, 28, 1, 0),   # 03:00 CEST
        utc(2027, 3, 28, 2, 0),   # 04:00 CEST
    ]


def test_nonexistent_local_time_does_not_crash():
    # Takvo vreme ne bi trebalo da postoji u rasporedu; vazno je samo da ne dodje do greske.
    result = parse_xmltv(tv(programme("20270328023000", title="Nemoguce")), "test.sr", BELGRADE)
    assert isinstance(result.programmes[0].start_utc, int)


def test_end_time_in_repeated_hour_is_not_before_start():
    data = tv(programme("20261025013000", "20261025023000", "Preko promene"))
    programme_ = parse_xmltv(data, "test.sr", BELGRADE).programmes[0]
    assert programme_.end_utc >= programme_.start_utc


# ---- Faza 8: pokvareni i zlonamerni podaci -----------------------------------------

def test_unknown_xml_encoding_is_a_parse_error_not_a_crash():
    data = b'<?xml version="1.0" encoding="UTF-J"?><tv></tv>'
    with pytest.raises(ParseError):
        parse_xmltv(data, "test.sr", BELGRADE)


def test_entity_definition_is_rejected_in_any_case_and_in_utf16():
    for text, encoding in (
        ('<!DOCTYPE tv [<!entity a "x">]><tv/>', "utf-8"),
        ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE tv [<!ENTITY a "x">]><tv/>', "utf-16"),
    ):
        with pytest.raises(ParseError):
            parse_xmltv(text.encode(encoding), "test.sr", BELGRADE)


def test_huge_fields_are_cut_to_a_sane_length():
    huge = "x" * 100_000
    data = tv(programme("20261106193000", "20261106200000", title=huge,
                        extra="<desc>%s</desc><category>%s</category>" % (huge, huge)))
    item = parse_xmltv(data, "test.sr", BELGRADE).programmes[0]
    assert len(item.title) == 300 and item.title.endswith("...")
    assert len(item.description) == 3000
    assert len(item.category) == 100


def test_random_damage_only_ever_raises_provider_errors():
    import random

    from app.providers.errors import ProviderError

    base = tv(*[programme("2026110%d193000" % (i % 9 + 1), "2026110%d203000" % (i % 9 + 1),
                          title="Naslov %d" % i) for i in range(15)])
    rng = random.Random(7)
    for _ in range(1500):
        data = bytearray(base)
        for _ in range(rng.randint(1, 5)):
            pos = rng.randrange(len(data))
            action = rng.random()
            if action < 0.4:
                data[pos] = rng.randrange(256)
            elif action < 0.7:
                del data[pos:pos + rng.randint(1, 30)]
            else:
                data[pos:pos] = bytes(rng.choice(b'<>&"=/ \x00\xff9') for _ in range(5))
        try:
            parse_xmltv(bytes(data), "test.sr", BELGRADE)
        except ProviderError:
            pass
