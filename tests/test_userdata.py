"""Testovi trajnih korisnickih podataka (Faza 6): omiljene, trajni kes rasporeda, oporavak."""

import os
import sqlite3
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.database.catalog import CatalogDatabase  # noqa: E402
from app.database.userdata import (  # noqa: E402
    CACHE_MAX_AGE_SECONDS,
    CACHE_MAX_ENTRIES,
    UserDatabase,
    UserDataError,
)
from app.models.channel import Channel  # noqa: E402
from app.models.schedule import Programme  # noqa: E402
from app.services.favourites_service import FavouritesService  # noqa: E402

NOW = 1_793_000_000
SHIPPED_CATALOG = os.path.join(ROOT, "data", "catalog_seed.db")


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "data" / "userdata.db")


def open_db(path, clock=None):
    return UserDatabase(path, clock=clock or Clock())


def programmes():
    return [
        Programme("Dnevnik", NOW, NOW + 1800, "Vesti dana", "Informativni"),
        Programme("Film \u0107\u010d\u0161\u0111\u017e", NOW + 1800, None),
    ]


# ---- omiljene ---------------------------------------------------------------

def test_new_database_is_created_with_missing_folder(db_path):
    store = open_db(db_path)
    assert os.path.isfile(db_path)
    assert store.favourite_ids() == []


def test_favourites_add_remove_and_order(db_path):
    clock = Clock()
    store = open_db(db_path, clock)
    store.add_favourite("RTS1.rs")
    clock.now += 10
    store.add_favourite("BBCOne.uk")
    store.add_favourite("RTS1.rs")  # dvaput ne pravi duplikat
    assert store.favourite_ids() == ["RTS1.rs", "BBCOne.uk"]
    assert store.is_favourite("RTS1.rs")
    store.remove_favourite("RTS1.rs")
    store.remove_favourite("nepostoji")  # bez greske
    assert not store.is_favourite("RTS1.rs")
    assert store.favourite_ids() == ["BBCOne.uk"]


def test_favourites_survive_restart(db_path):
    store = open_db(db_path)
    store.add_favourite("RTS1.rs")
    store.close()
    again = open_db(db_path)
    assert again.favourite_ids() == ["RTS1.rs"]


# ---- trajni kes -------------------------------------------------------------

def test_schedule_roundtrip_keeps_every_field_and_unicode(db_path):
    store = open_db(db_path)
    store.save_schedule("tvprofil", "rts1.sr", NOW, programmes())
    store.close()
    fetched_at, loaded = open_db(db_path).load_schedule("tvprofil", "rts1.sr")
    assert fetched_at == NOW
    assert loaded == programmes()


def test_missing_schedule_is_none(db_path):
    assert open_db(db_path).load_schedule("tvprofil", "nema") is None


def test_save_replaces_older_data_for_same_channel(db_path):
    store = open_db(db_path)
    store.save_schedule("tvprofil", "rts1.sr", NOW, programmes())
    store.save_schedule("tvprofil", "rts1.sr", NOW + 5, programmes()[:1])
    fetched_at, loaded = store.load_schedule("tvprofil", "rts1.sr")
    assert (fetched_at, len(loaded)) == (NOW + 5, 1)
    assert store.schedule_count() == 1


def test_old_schedules_are_pruned(db_path):
    clock = Clock()
    store = open_db(db_path, clock)
    store.save_schedule("tvprofil", "staro", NOW, programmes())
    clock.now = NOW + CACHE_MAX_AGE_SECONDS + 10
    store.save_schedule("tvprofil", "novo", clock.now, programmes())
    assert store.load_schedule("tvprofil", "staro") is None
    assert store.load_schedule("tvprofil", "novo") is not None


def test_cache_size_is_limited_and_newest_are_kept(db_path):
    store = open_db(db_path)
    for index in range(CACHE_MAX_ENTRIES + 5):
        store.save_schedule("tvprofil", "ch%d" % index, NOW + index, programmes())
    assert store.schedule_count() == CACHE_MAX_ENTRIES
    assert store.load_schedule("tvprofil", "ch0") is None
    assert store.load_schedule("tvprofil", "ch%d" % (CACHE_MAX_ENTRIES + 4)) is not None


@pytest.mark.parametrize(
    "payload",
    ["nije json", "{}", "[[1,2]]", '[["", 1, null, null, null]]',
     '[["A", "1", null, null, null]]', '[["A", 1, "2", null, null]]',
     '[["A", 1, null, 5, null]]', '[["A", true, null, null, null]]'],
)
def test_damaged_payload_is_dropped_not_raised(db_path, payload):
    store = open_db(db_path)
    store.save_schedule("tvprofil", "rts1.sr", NOW, programmes())
    connection = sqlite3.connect(db_path)
    connection.execute("UPDATE schedule_cache SET payload = ?", (payload,))
    connection.commit()
    connection.close()
    assert store.load_schedule("tvprofil", "rts1.sr") is None
    assert store.schedule_count() == 0  # neispravan red je obrisan


# ---- otvaranje i oporavak ----------------------------------------------------

def test_corrupt_file_is_moved_aside_and_new_database_works(db_path):
    os.makedirs(os.path.dirname(db_path))
    with open(db_path, "wb") as handle:
        handle.write(b"ovo nije sqlite baza" * 100)
    store = open_db(db_path)
    store.add_favourite("RTS1.rs")
    assert store.favourite_ids() == ["RTS1.rs"]
    backups = [n for n in os.listdir(os.path.dirname(db_path)) if ".corrupt-" in n]
    assert len(backups) == 1  # stari fajl nije obrisan


def test_database_from_newer_app_is_not_touched(db_path):
    os.makedirs(os.path.dirname(db_path))
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE favourite (catalog_id TEXT)")
    connection.execute("PRAGMA user_version = 99")
    connection.commit()
    connection.close()
    with pytest.raises(UserDataError):
        open_db(db_path)
    assert not [n for n in os.listdir(os.path.dirname(db_path)) if ".corrupt-" in n]


def test_unwritable_folder_is_reported(tmp_path):
    blocker = tmp_path / "fajl"
    blocker.write_text("x")
    with pytest.raises(UserDataError):
        UserDatabase(str(blocker / "podfolder" / "userdata.db"))


def test_database_error_after_open_becomes_userdataerror(db_path):
    store = open_db(db_path)
    store.close()
    with pytest.raises(UserDataError):
        store.favourite_ids()


def test_used_from_several_threads(db_path):
    store = open_db(db_path)
    errors = []

    def work(number):
        try:
            for index in range(20):
                store.add_favourite("ch%d.%d" % (number, index))
                store.save_schedule("tvprofil", "ch%d" % number, NOW + index, programmes())
        except Exception as error:  # pragma: no cover - prijavljuje se ispod
            errors.append(error)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(store.favourite_ids()) == 80


# ---- servis omiljenih -----------------------------------------------------------

class FakeCatalog:
    def __init__(self, channels):
        self.channels = {c.catalog_id: c for c in channels}

    def get_by_catalog_id(self, catalog_id):
        return self.channels.get(catalog_id)


RTS1 = Channel(1, "RTS1.rs", "RTS 1", "RS", "Serbia", None, 1)
BBC = Channel(2, "BBCOne.uk", "BBC One", "UK", "United Kingdom", "BBC Television", 0)


def test_favourites_service_toggle_and_sorted_list(db_path):
    service = FavouritesService(FakeCatalog([RTS1, BBC]), open_db(db_path))
    assert service.toggle(RTS1) is True
    assert service.toggle(BBC) is True
    assert service.is_favourite(RTS1)
    assert [c.name for c in service.list_channels().channels] == ["BBC One", "RTS 1"]
    assert service.toggle(RTS1) is False
    assert not service.is_favourite(RTS1)
    assert [c.catalog_id for c in service.list_channels().channels] == ["BBCOne.uk"]


def test_favourite_missing_from_catalog_is_counted_but_kept(db_path):
    store = open_db(db_path)
    store.add_favourite("RTS1.rs")
    store.add_favourite("ugasena.xx")
    result = FavouritesService(FakeCatalog([RTS1]), store).list_channels()
    assert [c.catalog_id for c in result.channels] == ["RTS1.rs"]
    assert result.missing == 1
    assert store.is_favourite("ugasena.xx")  # ne brise se bez korisnikove odluke


@pytest.mark.skipif(not os.path.isfile(SHIPPED_CATALOG), reason="nema kataloga")
def test_real_catalog_lookup_by_catalog_id():
    catalog = CatalogDatabase()
    try:
        match = catalog.find("rts1", 50).items
        assert match
        channel = match[0][0]
        found = catalog.get_by_catalog_id(channel.catalog_id)
        assert found == channel
        assert catalog.get_by_catalog_id("ovo.ne.postoji") is None
    finally:
        catalog.close()


def test_add_favourites_in_bulk_counts_only_new_and_clear_removes_all(db_path):
    store = open_db(db_path)
    store.add_favourite("RTS1.rs")
    assert store.add_favourites(["RTS1.rs", "BBCOne.uk", "HRT1.hr"]) == 2
    assert store.add_favourites(["BBCOne.uk"]) == 0
    assert store.add_favourites([]) == 0
    assert sorted(store.favourite_ids()) == ["BBCOne.uk", "HRT1.hr", "RTS1.rs"]
    assert store.clear_favourites() == 3
    assert store.favourite_ids() == [] and store.clear_favourites() == 0


@pytest.mark.skipif(not os.path.isfile(SHIPPED_CATALOG), reason="nema kataloga")
def test_channels_with_sources_are_sorted_by_country_and_name():
    catalog = CatalogDatabase()
    try:
        channels = catalog.channels_with_sources(["tvprofil"])
        assert len(channels) == 126 and all(c.source_count >= 1 for c in channels)
        keys = [(c.country_name.casefold(), c.name.casefold()) for c in channels]
        assert keys == sorted(keys)
        assert {c.country_code for c in channels} >= {"RS", "HR", "BA", "SI", "MK", "ME"}
        assert catalog.channels_with_sources([]) == []
        assert catalog.channels_with_sources(["nepoznat"]) == []
    finally:
        catalog.close()
