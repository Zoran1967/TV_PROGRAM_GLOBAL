"""Testovi Faze 7 (bez Kivy-ja): podesavanja, migracija baze, politika osvezavanja,
format vremena, zona uredjaja, prevodi i nazivi drzava."""

import datetime
import os
import sqlite3
import string
import sys
import types
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.database.userdata import USER_SCHEMA_VERSION, UserDatabase  # noqa: E402
from app.models.channel import Channel  # noqa: E402
from app.services.factory import (  # noqa: E402
    STORAGE_MEMORY,
    STORAGE_ON,
    STORAGE_UNAVAILABLE,
    create_services,
)
from app.services.settings_service import (  # noqa: E402
    DEFINITIONS,
    SettingsService,
    option_label_key,
    refresh_policy,
)
from app.strings import STRINGS, t  # noqa: E402
from app.theme import PALETTES, THEME_STYLES  # noqa: E402
from app.utils import devicezone  # noqa: E402
from app.utils.clockfmt import ClockFormat, format_date  # noqa: E402
from app.utils.countries import SERBIAN, country_name  # noqa: E402

CATALOG = os.path.join(ROOT, "data", "catalog_seed.db")
BELGRADE = ZoneInfo("Europe/Belgrade")
NEW_YORK = ZoneInfo("America/New_York")


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "userdata.db")


# ---- podesavanja: vrednosti i cuvanje ---------------------------------------------

def test_defaults_without_storage_are_serbian_dark_24h_station_time_source_refresh():
    service = SettingsService()
    assert service.all() == {
        "language": "sr", "theme": "dark", "time_format": "24h",
        "time_zone": "station", "refresh": "source",
    }
    assert service.persistent is False


def test_settings_survive_restart(db_path):
    store = UserDatabase(db_path)
    service = SettingsService(store)
    assert service.persistent
    assert service.set("language", "en") is True
    assert service.set("theme", "light") is True
    assert service.set("refresh", "manual") is True
    store.close()

    again = SettingsService(UserDatabase(db_path))
    assert again.get("language") == "en"
    assert again.get("theme") == "light"
    assert again.get("refresh") == "manual"
    assert again.get("time_format") == "24h"  # nepromenjeno ostaje podrazumevano


def test_invalid_stored_values_and_unknown_keys_are_ignored(db_path):
    store = UserDatabase(db_path)
    store.save_setting("language", "xx")
    store.save_setting("theme", "light")
    store.save_setting("iz_novije_verzije", "1")
    service = SettingsService(store)
    assert service.get("language") == "sr"
    assert service.get("theme") == "light"
    assert "iz_novije_verzije" not in service.all()


def test_set_rejects_unknown_key_and_value_without_changing_anything():
    service = SettingsService()
    with pytest.raises(ValueError):
        service.set("tema", "dark")
    with pytest.raises(ValueError):
        service.set("theme", "plava")
    assert service.get("theme") == "dark"


def test_without_storage_setting_applies_for_the_session_but_reports_not_saved():
    service = SettingsService()
    assert service.set("language", "en") is False
    assert service.get("language") == "en"


def test_storage_error_on_save_keeps_the_value_for_the_session():
    class Broken:
        def load_settings(self):
            return {}

        def save_setting(self, key, value):
            raise RuntimeError("disk pun")

    service = SettingsService(Broken())
    assert service.set("theme", "light") is False
    assert service.get("theme") == "light"


def test_storage_error_on_load_falls_back_to_defaults():
    class Broken:
        def load_settings(self):
            raise RuntimeError("ostecena baza")

    service = SettingsService(Broken())
    assert service.all()["language"] == "sr"


# ---- baza: migracija sa verzije 1 --------------------------------------------------

def test_new_database_has_settings_table_and_current_version(db_path):
    UserDatabase(db_path).close()
    connection = sqlite3.connect(db_path)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == USER_SCHEMA_VERSION == 2
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"favourite", "schedule_cache", "setting"} <= tables


def test_version_1_database_is_upgraded_and_keeps_its_data(db_path):
    connection = sqlite3.connect(db_path)
    connection.executescript(
        "CREATE TABLE favourite (catalog_id TEXT PRIMARY KEY, added_at INTEGER NOT NULL);"
        "CREATE TABLE schedule_cache (source_id TEXT NOT NULL, source_channel_id TEXT NOT NULL,"
        " fetched_at INTEGER NOT NULL, payload TEXT NOT NULL,"
        " PRIMARY KEY (source_id, source_channel_id));"
        "INSERT INTO favourite VALUES ('RTS1.rs', 100);"
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    store = UserDatabase(db_path)
    assert store.favourite_ids() == ["RTS1.rs"]  # omiljene su ostale
    store.save_setting("theme", "light")
    assert store.load_settings() == {"theme": "light"}
    store.close()
    assert sqlite3.connect(db_path).execute("PRAGMA user_version").fetchone()[0] == 2
    # ponovno otvaranje ne dira ni podatke ni podesavanja
    again = UserDatabase(db_path)
    assert again.favourite_ids() == ["RTS1.rs"] and again.load_settings() == {"theme": "light"}


def test_save_setting_overwrites_the_same_key(db_path):
    store = UserDatabase(db_path)
    store.save_setting("language", "en")
    store.save_setting("language", "sr")
    assert store.load_settings() == {"language": "sr"}


def test_factory_always_gives_settings_and_reports_storage_state(tmp_path):
    on = create_services(str(tmp_path / "a"))
    assert on.storage_state == STORAGE_ON and on.settings.persistent

    memory = create_services(None)
    assert memory.storage_state == STORAGE_MEMORY
    assert memory.settings is not None and not memory.settings.persistent

    blocker = tmp_path / "fajl"
    blocker.write_text("x")
    broken = create_services(str(blocker / "ne" / "moze"))
    assert broken.storage_state == STORAGE_UNAVAILABLE and broken.storage_detail
    assert broken.settings is not None and not broken.settings.persistent
    assert broken.favourites is None and broken.search is not None


# ---- osvezavanje: politika servisa rasporeda ---------------------------------------

from test_schedule_service import (  # noqa: E402
    CHANNEL,
    DAY,
    NOW,
    Clock,
    FakeProvider,
    service as make_service,
)


def test_refresh_policy_values():
    assert refresh_policy("source") == (None, False)
    assert refresh_policy("12h") == (12 * 3600, False)
    assert refresh_policy("24h") == (24 * 3600, False)
    assert refresh_policy("manual") == (None, True)


def test_default_policy_refetches_after_the_source_interval():
    clock = Clock(NOW)
    provider = FakeProvider(DAY, refresh=3600)
    svc = make_service(provider, clock=clock)
    svc.get_schedule(CHANNEL)
    clock.now = NOW + 4000
    outcome = svc.get_schedule(CHANNEL)
    assert provider.calls == 2
    assert outcome.refresh_seconds == 3600


def test_longer_user_interval_keeps_data_longer():
    clock = Clock(NOW)
    provider = FakeProvider(DAY, refresh=3600)
    svc = make_service(provider, clock=clock)
    svc.set_refresh_policy(min_seconds=12 * 3600)
    svc.get_schedule(CHANNEL)
    clock.now = NOW + 4000
    outcome = svc.get_schedule(CHANNEL)
    assert provider.calls == 1  # jos je sveze po izboru korisnika
    assert outcome.refresh_seconds == 12 * 3600
    clock.now = NOW + 13 * 3600
    svc.get_schedule(CHANNEL)
    assert provider.calls == 2


def test_user_interval_can_never_be_shorter_than_the_source_interval():
    clock = Clock(NOW)
    provider = FakeProvider(DAY, refresh=3600)
    svc = make_service(provider, clock=clock)
    svc.set_refresh_policy(min_seconds=60)
    svc.get_schedule(CHANNEL)
    clock.now = NOW + 600
    outcome = svc.get_schedule(CHANNEL)
    assert provider.calls == 1
    assert outcome.refresh_seconds == 3600


def test_manual_only_uses_saved_data_of_any_age_but_button_still_refreshes():
    clock = Clock(NOW)
    provider = FakeProvider(DAY, refresh=3600)
    svc = make_service(provider, clock=clock)
    svc.set_refresh_policy(manual_only=True)
    assert svc.manual_only
    svc.get_schedule(CHANNEL)  # nema nicega sacuvanog: preuzima se
    assert provider.calls == 1
    clock.now = NOW + 100 * 3600
    outcome = svc.get_schedule(CHANNEL)
    assert provider.calls == 1  # nema automatskog preuzimanja
    assert outcome.refresh_seconds == 3600  # a "Podaci su stari" se i dalje prijavljuje
    svc.get_schedule(CHANNEL, force=True)  # dugme Osvezi
    assert provider.calls == 2


def test_manual_only_does_not_retry_after_a_failed_refresh():
    from app.providers.errors import NetworkError

    clock = Clock(NOW)
    provider = FakeProvider(DAY, refresh=3600)
    svc = make_service(provider, clock=clock)
    svc.set_refresh_policy(manual_only=True)
    svc.get_schedule(CHANNEL)
    clock.now = NOW + 7200
    provider.error = NetworkError("nema mreze")
    stale = svc.get_schedule(CHANNEL, force=True)
    assert stale.stale and provider.calls == 2
    svc.get_schedule(CHANNEL)  # bez "force": ne pokusava ponovo
    assert provider.calls == 2


def test_switching_back_to_automatic_restores_source_interval():
    clock = Clock(NOW)
    provider = FakeProvider(DAY, refresh=3600)
    svc = make_service(provider, clock=clock)
    svc.set_refresh_policy(manual_only=True)
    svc.get_schedule(CHANNEL)
    svc.set_refresh_policy(None, False)
    clock.now = NOW + 4000
    svc.get_schedule(CHANNEL)
    assert provider.calls == 2


# ---- format vremena -----------------------------------------------------------------

def at(hour, minute, day=6, zone=BELGRADE):
    return datetime.datetime(2026, 11, day, hour, minute, tzinfo=zone)


@pytest.mark.parametrize("hour,minute,expected24,expected12", [
    (0, 5, "00:05", "12:05 AM"),
    (7, 30, "07:30", "7:30 AM"),
    (12, 0, "12:00", "12:00 PM"),
    (13, 7, "13:07", "1:07 PM"),
    (23, 59, "23:59", "11:59 PM"),
])
def test_clock_24_and_12_hour(hour, minute, expected24, expected12):
    assert ClockFormat(False).clock(at(hour, minute)) == expected24
    assert ClockFormat(True).clock(at(hour, minute)) == expected12


def test_device_zone_converts_time_and_dates():
    fmt = ClockFormat(False, NEW_YORK)
    assert fmt.converts
    assert fmt.clock(at(23, 30)) == "17:30"  # Beograd CET (UTC+1) -> Njujork EST (UTC-5)
    assert fmt.zone_label(at(23, 30)) == "EST"
    # 03:00 sutradan u stanici je jos "danas" (6.11.) u zoni uredjaja
    assert fmt.date_of(at(3, 0, day=7)) == datetime.date(2026, 11, 6)
    assert ClockFormat().date_of(at(3, 0, day=7)) == datetime.date(2026, 11, 7)


def test_without_zone_values_stay_in_their_own_zone():
    fmt = ClockFormat()
    assert not fmt.converts
    assert fmt.clock(at(9, 0)) == "09:00"
    assert fmt.zone_label(at(9, 0)) == "CET"


def test_dst_change_is_handled_in_the_display_zone():
    # 25.10.2026. Evropa prelazi na zimsko vreme; Njujork jos nije (to je 1.11.)
    summer = datetime.datetime(2026, 10, 24, 12, 0, tzinfo=BELGRADE)
    winter = datetime.datetime(2026, 10, 26, 12, 0, tzinfo=BELGRADE)
    fmt = ClockFormat(False, NEW_YORK)
    assert fmt.clock(summer) == "06:00"  # CEST (UTC+2) -> EDT (UTC-4)
    assert fmt.clock(winter) == "07:00"  # CET (UTC+1) -> EDT (UTC-4)


def test_format_date_per_language():
    day = datetime.date(2026, 11, 8)
    assert format_date(day, "sr") == "08.11.2026."
    assert format_date(day, "en") == "2026-11-08"
    assert format_date(None, "sr") == ""


# ---- zona uredjaja -------------------------------------------------------------------

def test_desktop_zone_from_tz_variable(monkeypatch):
    monkeypatch.setattr("app.utils.android_insets.is_android", lambda: False)
    monkeypatch.setenv("TZ", "Europe/Zagreb")
    assert devicezone.detect_device_zone_name() == "Europe/Zagreb"
    monkeypatch.setenv("TZ", "Nema/Takve")
    assert devicezone.detect_device_zone_name() is None


def _fake_jnius(zone_id=None, error=None):
    module = types.ModuleType("jnius")

    def autoclass(name):
        if error:
            raise error
        timezone = types.SimpleNamespace(
            getDefault=lambda: types.SimpleNamespace(getID=lambda: zone_id))
        return timezone

    module.autoclass = autoclass
    return module


def test_android_zone_from_system(monkeypatch):
    monkeypatch.setattr("app.utils.android_insets.is_android", lambda: True)
    monkeypatch.setitem(sys.modules, "jnius", _fake_jnius("Europe/Belgrade"))
    assert devicezone.detect_device_zone_name() == "Europe/Belgrade"


@pytest.mark.parametrize("zone_id", ["GMT+01:00", "", None, "Nesto/Nepoznato"])
def test_android_non_iana_or_missing_zone_is_not_guessed(monkeypatch, zone_id):
    monkeypatch.setattr("app.utils.android_insets.is_android", lambda: True)
    monkeypatch.setitem(sys.modules, "jnius", _fake_jnius(zone_id))
    assert devicezone.detect_device_zone_name() is None


def test_android_system_error_returns_none(monkeypatch):
    monkeypatch.setattr("app.utils.android_insets.is_android", lambda: True)
    monkeypatch.setitem(sys.modules, "jnius", _fake_jnius(error=RuntimeError("JNI greska")))
    assert devicezone.detect_device_zone_name() is None


# ---- prevodi i teme ------------------------------------------------------------------

def _placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_language_has_the_same_keys_and_placeholders_as_serbian():
    serbian = STRINGS["sr"]
    for language, table in STRINGS.items():
        assert set(table) == set(serbian), "kljucevi se razlikuju: %s" % language
        for key, text in table.items():
            assert _placeholders(text) == _placeholders(serbian[key]), (language, key)


def test_all_translations_are_filled_in():
    for language, table in STRINGS.items():
        for key, text in table.items():
            assert text.strip(), (language, key)


def test_language_names_and_setting_options_have_texts_in_every_language():
    for definition in DEFINITIONS:
        for value in definition.options:
            for language in STRINGS:
                assert not t(option_label_key(definition.key, value), language).startswith("[")
        for language in STRINGS:
            assert not t("setting_" + definition.key, language).startswith("[")


def test_language_setting_offers_exactly_the_available_languages():
    options = next(d for d in DEFINITIONS if d.key == "language").options
    assert set(options) == set(STRINGS)


def test_palettes_have_same_keys_and_readable_contrast():
    assert set(PALETTES["dark"]) == set(PALETTES["light"])
    assert set(THEME_STYLES) == set(PALETTES)
    assert set(next(d for d in DEFINITIONS if d.key == "theme").options) == set(PALETTES)

    def luminance(color):
        def channel(v):
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        r, g, b = (channel(v) for v in color[:3])
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def contrast(a, b):
        high, low = sorted((luminance(a), luminance(b)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    for name, palette in PALETTES.items():
        for text in ("gold", "text_muted"):
            for background in ("navy", "navy_light"):
                assert contrast(palette[text], palette[background]) >= 4.5, (name, text, background)


# ---- nazivi drzava ------------------------------------------------------------------

def test_every_catalog_country_has_a_serbian_name():
    connection = sqlite3.connect(CATALOG)
    codes = {row[0] for row in connection.execute("SELECT code FROM country")}
    assert codes - set(SERBIAN) == set(), "nema prevoda za: %s" % sorted(codes - set(SERBIAN))
    assert set(SERBIAN) - codes == set(), "prevod za drzavu koje nema u katalogu"


def test_country_name_by_language_and_fallback():
    channel = Channel(1, "RTS1.rs", "RTS 1", "RS", "Serbia")
    assert country_name(channel, "sr") == "Srbija"
    assert country_name(channel, "en") == "Serbia"
    assert country_name(channel, "xx") == "Serbia"
    unknown = Channel(2, "X.zz", "X", "ZZ", "Zedland")
    assert country_name(unknown, "sr") == "Zedland"  # nista se ne izmislja

