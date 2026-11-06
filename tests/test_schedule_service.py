"""Testovi servisa rasporeda. Svi podaci su IZMISLJENI test podaci."""

import datetime
import os
import sys
import threading
import time
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.models.channel import Channel  # noqa: E402
from app.models.schedule import ChannelSource, Programme  # noqa: E402
from app.providers.base import ProviderInfo, ScheduleProvider  # noqa: E402
from app.providers.errors import (  # noqa: E402
    EmptyScheduleError,
    HttpStatusError,
    InvalidSourceError,
    NetworkError,
    ParseError,
    RateLimitedError,
    ZoneUnavailableError,
)
from app.providers.registry import ProviderRegistry  # noqa: E402
from app.services import schedule_service as schedule_module  # noqa: E402
from app.services.schedule_service import ScheduleService, ScheduleStatus  # noqa: E402

BELGRADE = ZoneInfo("Europe/Belgrade")
UTC = datetime.timezone.utc
CHANNEL = Channel(1, "RTS1.rs", "RTS 1", "RS", "Serbia", None, 1)
SOURCE = ChannelSource("tvprofil", "rts1.sr", "Europe/Belgrade", 7, 0)


def utc(*args):
    return int(datetime.datetime(*args, tzinfo=UTC).timestamp())


def local(*args):
    return int(datetime.datetime(*args, tzinfo=BELGRADE).timestamp())


class FakeCatalog:
    def __init__(self, sources):
        self.sources = sources

    def sources_for(self, channel_id):
        return list(self.sources)


class FakeProvider(ScheduleProvider):
    def __init__(self, programmes=(), error=None, source_id="tvprofil", refresh=3600, delay=0.0):
        self.info = ProviderInfo(source_id, "TvProfil", "pending", "Izvor: test", "https://x", refresh)
        self.programmes = list(programmes)
        self.error = error
        self.calls = 0
        self.delay = delay

    def fetch_programmes(self, source):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return list(self.programmes)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


NOW = local(2026, 11, 6, 12, 0)  # 06.11.2026. 12:00 u Beogradu


def service(provider=None, sources=(SOURCE,), clock=None):
    providers = {provider.info.id: provider} if provider else {}
    return ScheduleService(FakeCatalog(sources), ProviderRegistry(providers), clock=clock or Clock(NOW))


DAY = [
    Programme("Juce uvece", local(2026, 11, 5, 23, 0), local(2026, 11, 6, 0, 30)),
    Programme("Jutro", local(2026, 11, 6, 6, 0), local(2026, 11, 6, 7, 0), "Opis jutra", "Informativni"),
    Programme("Dnevnik", local(2026, 11, 6, 19, 30), local(2026, 11, 6, 20, 0)),
    Programme("Nocni film", local(2026, 11, 6, 23, 30), local(2026, 11, 7, 1, 30)),
    Programme("Sutra", local(2026, 11, 7, 1, 30), local(2026, 11, 7, 2, 30)),
    Programme("Prekjuce", local(2026, 11, 5, 10, 0), local(2026, 11, 5, 11, 0)),
]


# ---- osnovni tok -------------------------------------------------------------

def test_no_source():
    outcome = service(None, sources=()).get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.NO_SOURCE


def test_source_exists_but_provider_is_not_loaded():
    outcome = service(None).get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.SOURCE_UNAVAILABLE
    assert "tvprofil" in outcome.detail


def test_todays_entries_in_local_time_including_overlap_with_midnight():
    provider = FakeProvider(DAY)
    outcome = service(provider).get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.OK
    assert [e.title for e in outcome.entries] == ["Juce uvece", "Jutro", "Dnevnik", "Nocni film"]
    assert outcome.local_date == datetime.date(2026, 11, 6)
    assert outcome.timezone == "Europe/Belgrade" and outcome.zone_label == "CET"
    assert outcome.source_name == "TvProfil" and outcome.license_status == "pending"
    dnevnik = outcome.entries[2]
    assert (dnevnik.start.hour, dnevnik.start.minute) == (19, 30)
    assert dnevnik.start.tzinfo is not None and dnevnik.start.utcoffset() == datetime.timedelta(hours=1)
    assert outcome.entries[1].description == "Opis jutra" and outcome.entries[1].category == "Informativni"


def test_programme_without_end_is_included_only_if_it_starts_today():
    provider = FakeProvider([
        Programme("Danas", local(2026, 11, 6, 10, 0), None),
        Programme("Juce", local(2026, 11, 5, 23, 59), None),
        Programme("Sutra", local(2026, 11, 7, 0, 0), None),
    ])
    outcome = service(provider).get_schedule(CHANNEL)
    assert [e.title for e in outcome.entries] == ["Danas"]
    assert outcome.entries[0].end is None


def test_day_follows_the_station_zone_not_utc():
    # 23:30 UTC 06.11. je vec 00:30 07.11. u Beogradu
    provider = FakeProvider(DAY)
    outcome = service(provider, clock=Clock(utc(2026, 11, 6, 23, 30))).get_schedule(CHANNEL)
    assert outcome.local_date == datetime.date(2026, 11, 7)
    assert [e.title for e in outcome.entries] == ["Nocni film", "Sutra"]


def test_day_with_25_hours_at_autumn_clock_change():
    provider = FakeProvider([
        Programme("Pre", local(2026, 10, 24, 23, 0), local(2026, 10, 25, 0, 30)),
        Programme("Veceras", local(2026, 10, 25, 23, 30), local(2026, 10, 26, 0, 10)),
        Programme("Sutra", local(2026, 10, 26, 0, 10), local(2026, 10, 26, 1, 0)),
    ])
    outcome = service(provider, clock=Clock(local(2026, 10, 25, 12, 0))).get_schedule(CHANNEL)
    assert [e.title for e in outcome.entries] == ["Pre", "Veceras"]


def test_no_programmes_for_todays_date():
    provider = FakeProvider([Programme("Davno", local(2026, 11, 1, 10, 0), local(2026, 11, 1, 11, 0))])
    outcome = service(provider).get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.NO_DATA_FOR_DATE
    assert outcome.local_date == datetime.date(2026, 11, 6)
    assert outcome.entries == ()


# ---- zona --------------------------------------------------------------------

@pytest.mark.parametrize("zone", [None, "", "Nema/Takve_Zone"])
def test_unknown_zone_is_reported_without_downloading(zone):
    provider = FakeProvider(DAY)
    src = ChannelSource("tvprofil", "rts1.sr", zone, 7, 0)
    outcome = service(provider, sources=(src,)).get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.ZONE_UNAVAILABLE
    assert provider.calls == 0
    assert outcome.entries == ()


# ---- kes -----------------------------------------------------------------------

def test_fresh_cache_is_reused_and_expired_cache_is_refreshed():
    provider = FakeProvider(DAY, refresh=600)
    clock = Clock(NOW)
    svc = service(provider, clock=clock)
    first = svc.get_schedule(CHANNEL)
    clock.now = NOW + 599
    second = svc.get_schedule(CHANNEL)
    assert provider.calls == 1 and second.fetched_at == first.fetched_at
    clock.now = NOW + 601
    third = svc.get_schedule(CHANNEL)
    assert provider.calls == 2 and third.fetched_at == NOW + 601
    assert not third.stale


def test_force_refresh_ignores_cache():
    provider = FakeProvider(DAY, refresh=600)
    svc = service(provider)
    svc.get_schedule(CHANNEL)
    svc.get_schedule(CHANNEL, force=True)
    assert provider.calls == 2


def test_failed_refresh_shows_stale_data_with_reason():
    provider = FakeProvider(DAY, refresh=600)
    clock = Clock(NOW)
    svc = service(provider, clock=clock)
    first = svc.get_schedule(CHANNEL)
    provider.error = NetworkError("nema veze")
    clock.now = NOW + 4000
    outcome = svc.get_schedule(CHANNEL)
    assert outcome.status == ScheduleStatus.OK and outcome.stale
    assert outcome.error_status == ScheduleStatus.NETWORK_ERROR
    assert outcome.fetched_at == first.fetched_at
    assert [e.title for e in outcome.entries] == [e.title for e in first.entries]


def test_stale_data_is_for_the_current_day_not_the_cached_day():
    provider = FakeProvider(DAY, refresh=600)
    clock = Clock(NOW)
    svc = service(provider, clock=clock)
    svc.get_schedule(CHANNEL)
    provider.error = NetworkError("nema veze")
    clock.now = local(2026, 11, 7, 12, 0)
    outcome = svc.get_schedule(CHANNEL)
    assert outcome.stale and outcome.local_date == datetime.date(2026, 11, 7)
    assert [e.title for e in outcome.entries] == ["Nocni film", "Sutra"]


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(schedule_module, "MAX_CACHE_ENTRIES", 3)
    provider = FakeProvider(DAY)
    clock = Clock(NOW)
    svc = service(provider, clock=clock)
    for i in range(6):
        clock.now = NOW + i
        svc.get_schedule(CHANNEL, sources=[ChannelSource("tvprofil", "kanal%d.sr" % i, "Europe/Belgrade", 7, 0)])
    assert len(svc._cache) == 3


# ---- greske izvora ---------------------------------------------------------------

@pytest.mark.parametrize("error, status", [
    (NetworkError("x"), ScheduleStatus.NETWORK_ERROR),
    (HttpStatusError(404), ScheduleStatus.HTTP_ERROR),
    (HttpStatusError(500), ScheduleStatus.HTTP_ERROR),
    (RateLimitedError(30), ScheduleStatus.RATE_LIMITED),
    (EmptyScheduleError("x"), ScheduleStatus.EMPTY),
    (ParseError("x"), ScheduleStatus.PARSE_ERROR),
    (InvalidSourceError("x"), ScheduleStatus.PARSE_ERROR),
    (ZoneUnavailableError("x"), ScheduleStatus.ZONE_UNAVAILABLE),
    (RuntimeError("neocekivano"), ScheduleStatus.ERROR),
])
def test_provider_errors_are_mapped_and_never_crash(error, status):
    outcome = service(FakeProvider(error=error)).get_schedule(CHANNEL)
    assert outcome.status == status
    assert outcome.entries == () and not outcome.stale


def test_http_status_is_reported():
    outcome = service(FakeProvider(error=HttpStatusError(404))).get_schedule(CHANNEL)
    assert outcome.http_status == 404


# ---- vise izvora -------------------------------------------------------------------

def test_second_source_is_used_when_first_fails():
    bad = FakeProvider(error=NetworkError("x"), source_id="prvi")
    good = FakeProvider(DAY, source_id="drugi")
    svc = ScheduleService(
        FakeCatalog([]), ProviderRegistry({"prvi": bad, "drugi": good}), clock=Clock(NOW))
    sources = [ChannelSource("prvi", "a", "Europe/Belgrade", 7, 0),
               ChannelSource("drugi", "b", "Europe/Belgrade", 7, 1)]
    outcome = svc.get_schedule(CHANNEL, sources=sources)
    assert outcome.status == ScheduleStatus.OK and good.calls == 1 and bad.calls == 1


def test_first_failure_is_reported_when_all_sources_fail():
    a = FakeProvider(error=NetworkError("x"), source_id="prvi")
    b = FakeProvider(error=ParseError("y"), source_id="drugi")
    svc = ScheduleService(FakeCatalog([]), ProviderRegistry({"prvi": a, "drugi": b}), clock=Clock(NOW))
    sources = [ChannelSource("prvi", "a", "Europe/Belgrade", 7, 0),
               ChannelSource("drugi", "b", "Europe/Belgrade", 7, 1)]
    assert svc.get_schedule(CHANNEL, sources=sources).status == ScheduleStatus.NETWORK_ERROR


def test_sources_are_read_from_the_catalog_when_not_given():
    provider = FakeProvider(DAY)
    assert service(provider).get_schedule(CHANNEL).status == ScheduleStatus.OK


# ---- niti --------------------------------------------------------------------------

def test_concurrent_requests_do_not_break_the_cache():
    provider = FakeProvider(DAY, delay=0.01)
    svc = service(provider)
    results = []

    def work():
        results.append(svc.get_schedule(CHANNEL).status)

    threads = [threading.Thread(target=work) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [ScheduleStatus.OK] * 12
