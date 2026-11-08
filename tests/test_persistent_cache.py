"""Testovi trajnog kesa rasporeda u ScheduleService (Faza 6). Svi podaci su IZMISLJENI."""

import datetime
import os
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.database.userdata import UserDatabase  # noqa: E402
from app.models.channel import Channel  # noqa: E402
from app.models.schedule import ChannelSource, Programme  # noqa: E402
from app.providers.base import ProviderInfo, ScheduleProvider  # noqa: E402
from app.providers.errors import NetworkError  # noqa: E402
from app.providers.registry import ProviderRegistry  # noqa: E402
from app.services.schedule_service import ScheduleService, ScheduleStatus  # noqa: E402

BELGRADE = ZoneInfo("Europe/Belgrade")
CHANNEL = Channel(1, "RTS1.rs", "RTS 1", "RS", "Serbia", None, 1)
SOURCE = ChannelSource("tvprofil", "rts1.sr", "Europe/Belgrade", 7, 0)


def local(*args):
    return int(datetime.datetime(*args, tzinfo=BELGRADE).timestamp())


NOW = local(2026, 11, 6, 12, 0)
DAY = [
    Programme("Jutro", local(2026, 11, 6, 6, 0), local(2026, 11, 6, 7, 0), "Opis", "Info"),
    Programme("Dnevnik", local(2026, 11, 6, 11, 30), local(2026, 11, 6, 12, 30)),
    Programme("Film", local(2026, 11, 6, 12, 30), local(2026, 11, 6, 14, 0)),
]


class Catalog:
    def sources_for(self, channel_id):
        return [SOURCE]


class Provider(ScheduleProvider):
    def __init__(self, error=None, refresh=3600):
        self.info = ProviderInfo("tvprofil", "TvProfil", "pending", "x", "y", refresh)
        self.error = error
        self.calls = 0

    def fetch_programmes(self, source):
        self.calls += 1
        if self.error:
            raise self.error
        return list(DAY)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def make(store, provider, clock):
    return ScheduleService(Catalog(), ProviderRegistry({"tvprofil": provider}), clock=clock, store=store)


def store_at(tmp_path, clock):
    return UserDatabase(str(tmp_path / "u.db"), clock=clock)


def test_successful_download_is_written_to_disk(tmp_path):
    clock = Clock(NOW)
    store = store_at(tmp_path, clock)
    make(store, Provider(), clock).get_schedule(CHANNEL)
    fetched_at, programmes = store.load_schedule("tvprofil", "rts1.sr")
    assert fetched_at == NOW
    assert programmes == DAY


def test_after_restart_fresh_data_is_used_without_network(tmp_path):
    clock = Clock(NOW)
    store = store_at(tmp_path, clock)
    make(store, Provider(), clock).get_schedule(CHANNEL)

    clock.now = NOW + 600  # nova sesija: prazna memorija, 10 min kasnije
    provider = Provider()
    outcome = make(store, provider, clock).get_schedule(CHANNEL)
    assert provider.calls == 0
    assert outcome.status == ScheduleStatus.OK
    assert outcome.fetched_at == NOW
    assert outcome.current.title == "Dnevnik"


def test_after_restart_old_data_is_refreshed(tmp_path):
    clock = Clock(NOW)
    store = store_at(tmp_path, clock)
    make(store, Provider(), clock).get_schedule(CHANNEL)

    clock.now = NOW + 7200  # starije od roka osvezavanja izvora (3600 s)
    provider = Provider()
    outcome = make(store, provider, clock).get_schedule(CHANNEL)
    assert provider.calls == 1
    assert outcome.status == ScheduleStatus.OK
    assert outcome.fetched_at == NOW + 7200
    assert store.load_schedule("tvprofil", "rts1.sr")[0] == NOW + 7200


def test_offline_after_restart_shows_saved_data_as_stale_with_reason(tmp_path):
    clock = Clock(NOW)
    store = store_at(tmp_path, clock)
    make(store, Provider(), clock).get_schedule(CHANNEL)

    clock.now = NOW + 7200
    outcome = make(store, Provider(error=NetworkError("nema veze")), clock).get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.OK
    assert outcome.stale is True
    assert outcome.error_status == ScheduleStatus.NETWORK_ERROR
    assert outcome.fetched_at == NOW  # prikazuje se pravo vreme preuzimanja, ne novo
    # neuspelo osvezavanje ne prepisuje sacuvane podatke
    assert store.load_schedule("tvprofil", "rts1.sr")[0] == NOW


def test_offline_without_saved_data_is_an_error_not_invented_schedule(tmp_path):
    clock = Clock(NOW)
    outcome = make(store_at(tmp_path, clock), Provider(error=NetworkError("nema veze")), clock).get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.NETWORK_ERROR
    assert outcome.entries == ()


def test_refresh_view_uses_saved_data_without_network(tmp_path):
    clock = Clock(NOW)
    store = store_at(tmp_path, clock)
    make(store, Provider(), clock).get_schedule(CHANNEL)

    clock.now = NOW + 1800  # 12:30, "Film" pocinje
    provider = Provider()
    view = make(store, provider, clock).refresh_view(CHANNEL, [SOURCE])
    assert provider.calls == 0
    assert view.current.title == "Film"


def test_saved_data_from_the_future_is_ignored(tmp_path):
    clock = Clock(NOW)
    store = store_at(tmp_path, clock)
    store.save_schedule("tvprofil", "rts1.sr", NOW + 86400, DAY)  # sat telefona je kasnije vracen
    provider = Provider()
    outcome = make(store, provider, clock).get_schedule(CHANNEL)
    assert provider.calls == 1
    assert outcome.fetched_at == NOW


def test_broken_store_does_not_break_the_schedule(tmp_path):
    clock = Clock(NOW)
    store = store_at(tmp_path, clock)
    store.close()  # svaki poziv baze sada javlja gresku
    provider = Provider()
    service = make(store, provider, clock)
    outcome = service.get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.OK
    assert service.get_schedule(CHANNEL).status == ScheduleStatus.OK
    assert provider.calls == 1  # drugi put iz memorije


def test_without_store_behaviour_is_unchanged():
    clock = Clock(NOW)
    provider = Provider()
    service = ScheduleService(Catalog(), ProviderRegistry({"tvprofil": provider}), clock=clock)
    assert service.get_schedule(CHANNEL).status == ScheduleStatus.OK
    assert provider.calls == 1
