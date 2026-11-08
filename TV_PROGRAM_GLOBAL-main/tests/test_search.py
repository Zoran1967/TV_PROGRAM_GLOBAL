"""Testovi pretrage stanica (Faza 3): normalizacija, rangiranje, dvosmislenost."""

import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for extra in (ROOT, os.path.join(ROOT, "tools")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from app.database.catalog import CatalogDatabase, CatalogError  # noqa: E402
from app.services.search_service import (  # noqa: E402
    ChannelSearchService,
    SearchStatus,
)
from app.utils.text import normalize_key, normalize_text  # noqa: E402
from build_catalog import build_catalog  # noqa: E402

SHIPPED_CATALOG = os.path.join(ROOT, "data", "catalog_seed.db")


def channel(id_, name, country, alt="", network="", closed="", nsfw="FALSE"):
    return {
        "id": id_, "name": name, "alt_names": alt, "network": network,
        "country": country, "is_nsfw": nsfw, "closed": closed,
    }


COUNTRIES = [
    {"name": n, "code": c}
    for c, n in [
        ("RS", "Serbia"), ("SN", "Senegal"), ("CH", "Switzerland"),
        ("UK", "United Kingdom"), ("US", "United States"), ("TR", "Turkiye"),
        ("RO", "Romania"), ("BA", "Bosnia and Herzegovina"), ("MX", "Mexico"),
        ("IN", "India"), ("HR", "Croatia"), ("FR", "France"),
    ]
]

FIXTURE_CHANNELS = [
    channel("RTS1.rs", "RTS 1", "RS", alt="РТС 1"),
    channel("RTS1.sn", "RTS 1", "SN"),
    channel("RTS1.ch", "RTS 1", "CH"),
    channel("RTS2.rs", "RTS 2", "RS"),
    channel("BBCOne.uk", "BBC One", "UK", alt="BBC1;BBC Television", network="BBC Television"),
    channel("CNN.us", "CNN", "US", network="Cable News Network"),
    channel("CNNInternational.us", "CNN International", "US", alt="CNNi"),
    channel("CNNTurk.tr", "CNN Turk", "TR"),
    channel("DjakTV.rs", "Djak TV", "RS", alt="Đak ТВ"),
    channel("B1.rs", "B1", "RS"),
    channel("B1.ro", "B1", "RO"),
    channel("B1TV.ba", "B1 TV", "BA"),
    channel("B15Fresnillo.mx", "B15 Fresnillo", "MX"),
    channel("MixTV1.rs", "Mix TV", "RS"),
    channel("MixTV2.rs", "Mix TV", "RS"),
    channel("ArenaSport1.hr", "Arena Sport 1", "HR"),
    channel("StarSports2Hindi.in", "Star Sports 2 Hindi", "IN", alt="Sports18 1"),
    channel("Old.rs", "Old TV", "RS", closed="2020-01-01"),
    channel("Adult.fr", "Adult TV", "FR", nsfw="TRUE"),
    channel("Nowhere.zz", "Nowhere TV", "ZZ"),
    channel("Symbols.rs", "+++", "RS"),
]


@pytest.fixture(scope="module")
def stats_and_service(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("katalog") / "test_catalog.db")
    stats = build_catalog(FIXTURE_CHANNELS, COUNTRIES, path, meta={"source_commit": "test"})
    catalog = CatalogDatabase(path)
    yield stats, ChannelSearchService(catalog), catalog, path
    catalog.close()


@pytest.fixture
def service(stats_and_service):
    return stats_and_service[1]


def ids(outcome):
    return [result.channel.catalog_id for result in outcome.results]


# ---- normalizacija -----------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("RTS 1", "rts1"),
        ("rts-1", "rts1"),
        ("РТС 1", "rts1"),
        ("Đak ТВ", "djaktv"),
        ("Ђак", "djak"),
        ("Čaršija", "carsija"),
        ("Ћирилица", "cirilica"),
        ("  BBC   One ", "bbcone"),
        ("Łódź", "lodz"),
        ("%%", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_key(text, expected):
    assert normalize_key(text) == expected


def test_normalize_text_keeps_word_boundaries():
    assert normalize_text("Cafe&Club") == "cafe club"
    assert normalize_text("  RTS-1  HD ") == "rts 1 hd"


# ---- izrada kataloga ---------------------------------------------------

def test_builder_skips_closed_nsfw_unknown_country_and_empty_names(stats_and_service):
    stats, _service, catalog, _path = stats_and_service
    assert stats["ukupno_u_izvoru"] == len(FIXTURE_CHANNELS)
    assert stats["preskoceno_ugaseno"] == 1
    assert stats["preskoceno_nsfw"] == 1
    assert stats["preskoceno_nepoznata_zemlja"] == 1
    assert stats["preskoceno_bez_kljuca"] == 1
    assert stats["kanala"] == len(FIXTURE_CHANNELS) - 4
    assert catalog.channel_count() == stats["kanala"]


# ---- poznati primeri ---------------------------------------------------

def test_exact_name_with_country(service):
    outcome = service.search("BBC One")
    assert outcome.status == SearchStatus.OK
    assert ids(outcome) == ["BBCOne.uk"]
    assert outcome.results[0].channel.country_name == "United Kingdom"


def test_alternative_name_is_found_and_reported(service):
    outcome = service.search("BBC1")
    assert ids(outcome) == ["BBCOne.uk"]
    assert outcome.results[0].matched_alias == "BBC1"


def test_abbreviation_without_space_matches_name_with_space(service):
    assert "RTS1.rs" in ids(service.search("RTS1"))


def test_serbian_cyrillic_query(service):
    assert set(ids(service.search("РТС 1"))) == {"RTS1.rs", "RTS1.sn", "RTS1.ch"}


def test_diacritic_and_dj_variants(service):
    for query in ("Đak", "Djak", "Ђак", "djak tv"):
        assert ids(service.search(query)) == ["DjakTV.rs"], query


def test_query_matches_start_of_a_later_word(service):
    assert "BBCOne.uk" in ids(service.search("one"))


def test_no_junk_from_the_middle_of_words(service):
    # "Sports18 1" sadrzi "rts1" samo preko granice reci i ne sme da se pojavi
    outcome = service.search("RTS1")
    assert set(ids(outcome)) == {"RTS1.rs", "RTS1.sn", "RTS1.ch"}
    assert len(outcome.results) == 3


def test_contains_is_only_a_fallback(service):
    assert ids(service.search("ena sport")) == ["ArenaSport1.hr"]
    assert "ArenaSport1.hr" in ids(service.search("arena"))


# ---- rangiranje --------------------------------------------------------

def test_exact_match_comes_before_longer_names(service):
    names = [result.channel.name for result in service.search("B1").results]
    assert names[:2] == ["B1", "B1"]
    assert "B1 TV" in names and "B15 Fresnillo" in names
    assert names.index("B1 TV") < names.index("B15 Fresnillo")


def test_cnn_returns_several_countries_exact_first(service):
    outcome = service.search("CNN")
    assert ids(outcome)[0] == "CNN.us"
    assert {result.channel.country_code for result in outcome.results} == {"US", "TR"}


# ---- dvosmislenost -----------------------------------------------------

def test_same_name_in_different_countries_is_not_collapsed(service):
    outcome = service.search("RTS 1")
    assert [r.channel.name for r in outcome.results] == ["RTS 1"] * 3
    assert {r.channel.country_name for r in outcome.results} == {
        "Serbia", "Senegal", "Switzerland",
    }
    assert not any(result.needs_id for result in outcome.results)


def test_same_name_in_same_country_needs_catalog_id(service):
    outcome = service.search("Mix TV")
    assert len(outcome.results) == 2
    assert all(result.needs_id for result in outcome.results)
    assert {result.channel.catalog_id for result in outcome.results} == {
        "MixTV1.rs", "MixTV2.rs",
    }


# ---- nepostojeci, prazni i los unos ------------------------------------

def test_nonexistent_channel(service):
    assert service.search("xqzvjk").status == SearchStatus.NOT_FOUND


@pytest.mark.parametrize("query", ["", "   ", None, "%%", "---", "_"])
def test_empty_queries(service, query):
    assert service.search(query).status == SearchStatus.EMPTY_QUERY


def test_single_character_is_too_short(service):
    assert service.search("a").status == SearchStatus.TOO_SHORT


@pytest.mark.parametrize(
    "query",
    ["'; DROP TABLE channel; --", "%", "r_s", "\" OR 1=1", "\x00rts", "x" * 5000],
)
def test_hostile_input_is_harmless(stats_and_service, query):
    _stats, service, catalog, _path = stats_and_service
    before = catalog.channel_count()
    outcome = service.search(query)
    assert outcome.status in set(SearchStatus)
    assert catalog.channel_count() == before


def test_closed_nsfw_and_unknown_country_channels_are_not_searchable(service):
    for query in ("Old TV", "Adult TV", "Nowhere TV"):
        assert service.search(query).status == SearchStatus.NOT_FOUND


# ---- ogranicenje broja rezultata ---------------------------------------

def test_result_limit_and_truncation(tmp_path):
    rows = [channel("T%02d.rs" % i, "Test %02d" % i, "RS") for i in range(60)]
    path = str(tmp_path / "many.db")
    build_catalog(rows, COUNTRIES, path)
    catalog = CatalogDatabase(path)
    try:
        limited = ChannelSearchService(catalog, limit=50).search("test")
        assert len(limited.results) == 50 and limited.truncated
        full = ChannelSearchService(catalog, limit=100).search("test")
        assert len(full.results) == 60 and not full.truncated
    finally:
        catalog.close()


# ---- greske kataloga ---------------------------------------------------

def test_missing_catalog_file(tmp_path):
    with pytest.raises(CatalogError):
        CatalogDatabase(str(tmp_path / "nema.db"))


def test_wrong_schema_version(tmp_path):
    path = str(tmp_path / "stara.db")
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 99")
    connection.commit()
    connection.close()
    with pytest.raises(CatalogError):
        CatalogDatabase(path)


def test_corrupt_catalog_file(tmp_path):
    path = tmp_path / "pokvarena.db"
    path.write_bytes(b"ovo nije sqlite baza" * 100)
    with pytest.raises(CatalogError):
        CatalogDatabase(str(path))


def test_database_error_during_search_is_reported(stats_and_service):
    class Broken:
        def find(self, key, limit):
            raise sqlite3.OperationalError("disk I/O error")

    outcome = ChannelSearchService(Broken()).search("rts")
    assert outcome.status == SearchStatus.CATALOG_ERROR


def test_catalog_is_read_only(stats_and_service):
    _stats, _service, catalog, _path = stats_and_service
    with pytest.raises(sqlite3.OperationalError):
        catalog._connection.execute("DELETE FROM channel")


# ---- ugradjeni katalog (data/catalog_seed.db) --------------------------

shipped = pytest.mark.skipif(
    not os.path.isfile(SHIPPED_CATALOG), reason="data/catalog_seed.db ne postoji"
)


@pytest.fixture(scope="module")
def real_service():
    catalog = CatalogDatabase(SHIPPED_CATALOG)
    yield ChannelSearchService(catalog)
    catalog.close()


@shipped
def test_shipped_catalog_metadata():
    catalog = CatalogDatabase(SHIPPED_CATALOG)
    try:
        assert catalog.channel_count() > 20000
        meta = catalog.meta()
        assert "CC0" in meta["license"]
        assert len(meta["source_commit"]) == 40
    finally:
        catalog.close()


@shipped
@pytest.mark.parametrize(
    "query, first_id, country",
    [
        ("BBC One", "BBCOne.uk", "United Kingdom"),
        ("HRT1", "HRT1.hr", "Croatia"),
        ("Đak", "DjakTV.rs", "Serbia"),
    ],
)
def test_shipped_catalog_known_channels(real_service, query, first_id, country):
    outcome = real_service.search(query)
    assert outcome.status == SearchStatus.OK
    assert outcome.results[0].channel.catalog_id == first_id
    assert outcome.results[0].channel.country_name == country


@shipped
@pytest.mark.parametrize("query", ["RTS 1", "RTS1", "РТС 1"])
def test_shipped_catalog_rts1_is_ambiguous_across_countries(real_service, query):
    outcome = real_service.search(query)
    found = {result.channel.catalog_id for result in outcome.results}
    assert "RTS1.rs" in found
    assert len({result.channel.country_code for result in outcome.results}) >= 2


@shipped
def test_shipped_catalog_cnn_has_many_countries(real_service):
    outcome = real_service.search("CNN")
    assert outcome.results[0].channel.catalog_id == "CNN.us"
    assert len({result.channel.country_code for result in outcome.results}) >= 5


@shipped
def test_shipped_catalog_short_name_b1(real_service):
    assert "B1.rs" in {r.channel.catalog_id for r in real_service.search("B1").results}


@shipped
def test_shipped_catalog_nonexistent_channel(real_service):
    assert real_service.search("xqzvjk").status == SearchStatus.NOT_FOUND
