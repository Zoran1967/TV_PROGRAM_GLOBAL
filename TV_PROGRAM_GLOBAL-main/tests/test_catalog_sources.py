"""Testovi povezivanja TvProfil kanala sa katalogom i citanja izvora iz kataloga."""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for extra in (ROOT, os.path.join(ROOT, "tools")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from app.database.catalog import CatalogDatabase  # noqa: E402
from app.providers.xmltv import load_zone  # noqa: E402
from app.services.search_service import ChannelSearchService  # noqa: E402
from build_catalog import build_catalog  # noqa: E402

SHIPPED = os.path.join(ROOT, "data", "catalog_seed.db")

COUNTRIES = [{"code": c, "name": n} for c, n in [
    ("RS", "Serbia"), ("HR", "Croatia"), ("SI", "Slovenia"), ("BA", "Bosnia and Herzegovina"),
    ("ME", "Montenegro"), ("MK", "North Macedonia"), ("UK", "United Kingdom"), ("DE", "Germany")]]


def ch(id_, name, country, alt=""):
    return {"id": id_, "name": name, "alt_names": alt, "network": "", "country": country,
            "is_nsfw": "FALSE", "closed": ""}


CHANNELS = [
    ch("RTS1.rs", "RTS 1", "RS"),
    ch("PinkPlus.rs", "Pink Plus", "RS"),
    ch("B92.rs", "B92", "RS"),
    ch("HRT1.hr", "HRT 1", "HR"),
    ch("RTL.hr", "RTL", "HR"),
    ch("TVSLO1.si", "TV SLO 1", "SI"),
    ch("Dvojnik1.rs", "Dvojnik", "RS"),
    ch("Dvojnik2.rs", "Dvojnik", "RS"),
    ch("Konflikt.rs", "Konflikt", "RS"),
    ch("BBCOne.uk", "BBC One", "UK"),
    ch("RTS1.hr", "RTS 1", "HR"),          # isto ime u drugoj drzavi
    ch("NTV.rs", "NTV", "RS", alt="Novosadska TV"),
]


def tv(xmltv_id, name, days=7):
    return {"xmltv_id": xmltv_id, "name": name, "days_available": str(days)}


TVPROFIL = [
    tv("rts1.sr", "RTS1"),                    # naziv: "rts1" = "RTS 1" (RS)
    tv("pink-plus.sr", "PINK PLUS"),
    tv("b92.sr", "O2"),                       # samo preko ID-ja: b92 = B92
    tv("htv1.hr", "HTV1"),                    # naziv se razlikuje -> override
    tv("rtl.hr", "RTL"),
    tv("slo1.si", "SLO1", 0),                 # izvor kaze da nema podataka
    tv("dvojnik.sr", "Dvojnik"),              # vise stanica u katalogu
    tv("konflikt.sr", "Konflikt"),
    tv("konflikt-2.sr", "Konflikt"),          # dva TvProfil kanala za istu stanicu
    tv("nema-takve.sr", "Nema Takve"),
    tv("sport-1.sport", "Sport 1"),           # oznaka bez drzave: zona nepoznata
    tv("bbc1.uk", "BBC1"),                    # drzava nije u podrzanom spisku
    tv("niska-televizija.sr", "NTV"),         # rucno iskljuceno
    tv("neko.sr", "Neko"),                    # override ka nepostojecoj stanici
]
OVERRIDES = {
    "htv1.hr": "HRT1.hr",
    "niska-televizija.sr": "",
    "neko.sr": "NePostoji.rs",
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("izvori") / "k.db")
    stats = build_catalog(CHANNELS, COUNTRIES, path, tvprofil_rows=TVPROFIL, tvprofil_overrides=OVERRIDES)
    catalog = CatalogDatabase(path)
    yield stats, catalog
    catalog.close()


def status_of(stats, xmltv_id):
    return next(e["status"] for e in stats["_tvprofil_report"] if e["xmltv_id"] == xmltv_id)


def sources_of(catalog, catalog_id):
    row = catalog._connection.execute(
        "SELECT id FROM channel WHERE catalog_id = ?", (catalog_id,)).fetchone()
    assert row is not None, "stanica %s ne postoji u katalogu" % catalog_id
    return catalog.sources_for(row[0])


def test_name_match_and_zone(built):
    stats, catalog = built
    sources = sources_of(catalog, "RTS1.rs")
    assert [(s.source_id, s.source_channel_id, s.timezone, s.days_available) for s in sources] == [
        ("tvprofil", "rts1.sr", "Europe/Belgrade", 7)]
    assert status_of(stats, "rts1.sr") == "povezano"
    assert status_of(stats, "pink-plus.sr") == "povezano"


def test_match_through_the_id_slug(built):
    stats, catalog = built
    assert status_of(stats, "b92.sr") == "povezano"
    assert sources_of(catalog, "B92.rs")[0].source_channel_id == "b92.sr"


def test_same_name_in_another_country_is_not_linked(built):
    _stats, catalog = built
    assert sources_of(catalog, "RTS1.hr") == []


def test_override_links_channels_with_different_names(built):
    stats, catalog = built
    assert status_of(stats, "htv1.hr") == "povezano"
    source = sources_of(catalog, "HRT1.hr")[0]
    assert (source.source_channel_id, source.timezone) == ("htv1.hr", "Europe/Zagreb")


def test_blocked_override_stays_unlinked(built):
    stats, catalog = built
    assert status_of(stats, "niska-televizija.sr") == "rucno_iskljuceno"
    assert sources_of(catalog, "NTV.rs") == []


def test_override_to_unknown_catalog_channel(built):
    stats, _catalog = built
    assert status_of(stats, "neko.sr") == "override_nepoznat_kanal"


def test_ambiguous_conflicting_empty_and_unsupported_stay_unlinked(built):
    stats, catalog = built
    assert status_of(stats, "dvojnik.sr") == "vise_poklapanja"
    assert status_of(stats, "konflikt.sr") == "sukob_vise_kanala"
    assert status_of(stats, "konflikt-2.sr") == "sukob_vise_kanala"
    assert status_of(stats, "slo1.si") == "izvor_nema_podataka"
    assert status_of(stats, "nema-takve.sr") == "bez_poklapanja"
    assert status_of(stats, "sport-1.sport") == "nepodrzana_oznaka"
    assert status_of(stats, "bbc1.uk") == "nepodrzana_oznaka"
    for catalog_id in ("Dvojnik1.rs", "Dvojnik2.rs", "Konflikt.rs", "TVSLO1.si", "BBCOne.uk"):
        assert sources_of(catalog, catalog_id) == []


def test_stats_add_up(built):
    stats, _catalog = built
    statuses = [e["status"] for e in stats["_tvprofil_report"]]
    assert len(statuses) == len(TVPROFIL) == stats["tvprofil_u_spisku"]
    assert statuses.count("povezano") == stats["tvprofil_povezano"] == 5
    assert "" not in statuses


def test_search_results_know_if_a_schedule_source_exists(built):
    _stats, catalog = built
    service = ChannelSearchService(catalog)
    by_id = {r.channel.catalog_id: r.channel for r in service.search("RTS 1").results}
    assert by_id["RTS1.rs"].source_count == 1
    assert by_id["RTS1.hr"].source_count == 0


def test_tvprofil_source_id_is_a_safe_identifier(built):
    _stats, catalog = built
    for catalog_id in ("RTS1.rs", "PinkPlus.rs", "B92.rs", "HRT1.hr", "RTL.hr"):
        for source in sources_of(catalog, catalog_id):
            assert re.fullmatch(r"[a-z0-9][a-z0-9.\-]{0,80}", source.source_channel_id)


# ---- ugradjeni katalog ----------------------------------------------------------

shipped = pytest.mark.skipif(not os.path.isfile(SHIPPED), reason="data/catalog_seed.db ne postoji")


@pytest.fixture(scope="module")
def real():
    catalog = CatalogDatabase(SHIPPED)
    yield catalog
    catalog.close()


@shipped
def test_shipped_catalog_has_linked_channels(real):
    rows = real._connection.execute(
        "SELECT ch.catalog_id, s.source_id, s.source_channel_id, s.timezone, s.days_available "
        "FROM channel_source s JOIN channel ch ON ch.id = s.channel_id").fetchall()
    assert len(rows) >= 100
    assert real.meta()["tvprofil_linked"] == str(len(rows))
    assert {r[1] for r in rows} == {"tvprofil"}
    assert all(r[4] and r[4] >= 1 for r in rows)
    assert len({r[2] for r in rows}) == len(rows)


@shipped
def test_shipped_catalog_source_ids_and_zones_are_valid(real):
    rows = real._connection.execute(
        "SELECT source_channel_id, timezone FROM channel_source").fetchall()
    for source_channel_id, timezone in rows:
        assert re.fullmatch(r"[a-z0-9][a-z0-9.\-]{0,80}", source_channel_id), source_channel_id
        load_zone(timezone)


@shipped
@pytest.mark.parametrize("catalog_id, source_id, zone", [
    ("RTS1.rs", "rts1.sr", "Europe/Belgrade"),
    ("RTS2.rs", "rts2.sr", "Europe/Belgrade"),
    ("HRT1.hr", "htv1.hr", "Europe/Zagreb"),
    ("TVSLO1.si", "slo1.si", "Europe/Ljubljana"),
    ("BHT1.ba", "bht1.ba", "Europe/Sarajevo"),
    ("MRT1.mk", "mrt1.mk", "Europe/Skopje"),
    ("TVCG1.me", "tvcg1.cg", "Europe/Podgorica"),
])
def test_shipped_catalog_known_links(real, catalog_id, source_id, zone):
    channel = real._connection.execute(
        "SELECT id FROM channel WHERE catalog_id = ?", (catalog_id,)).fetchone()
    sources = real.sources_for(channel[0])
    assert [(s.source_channel_id, s.timezone) for s in sources] == [(source_id, zone)]


@shipped
def test_shipped_catalog_excluded_channels_have_no_source(real):
    for catalog_id in ("NTV.rs", "BBCOne.uk", "OKanal.ba", "CNN.us"):
        channel = real._connection.execute(
            "SELECT id FROM channel WHERE catalog_id = ?", (catalog_id,)).fetchone()
        assert real.sources_for(channel[0]) == [], catalog_id


@shipped
def test_shipped_catalog_search_shows_source_availability(real):
    service = ChannelSearchService(real)
    by_country = {r.channel.country_code: r.channel for r in service.search("RTS 1").results}
    assert by_country["RS"].source_count == 1
    assert by_country["SN"].source_count == 0
