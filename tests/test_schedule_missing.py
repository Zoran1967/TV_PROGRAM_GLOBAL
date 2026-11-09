"""Stanica za koju izvor nema fajl (404) se ne trazi iznova pri svakom otvaranju."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from app.providers.errors import HttpStatusError, NetworkError  # noqa: E402
from app.services import schedule_service as module  # noqa: E402
from app.services.schedule_service import ScheduleStatus  # noqa: E402
from test_schedule_service import CHANNEL, DAY, NOW, Clock, FakeProvider, service  # noqa: E402


def test_404_is_remembered_and_the_network_is_not_asked_again():
    provider = FakeProvider(error=HttpStatusError(404))
    clock = Clock(NOW)
    svc = service(provider, clock=clock)
    first = svc.get_schedule(CHANNEL)
    clock.now += 3600
    second = svc.get_schedule(CHANNEL)
    assert provider.calls == 1
    assert first.status == second.status == ScheduleStatus.HTTP_ERROR
    assert second.http_status == 404


def test_it_is_asked_again_after_the_window():
    provider = FakeProvider(error=HttpStatusError(404))
    clock = Clock(NOW)
    svc = service(provider, clock=clock)
    svc.get_schedule(CHANNEL)
    clock.now += module.MISSING_SOURCE_SECONDS + 1
    svc.get_schedule(CHANNEL)
    assert provider.calls == 2


def test_manual_refresh_asks_again_after_a_minute_but_not_sooner():
    provider = FakeProvider(error=HttpStatusError(404))
    clock = Clock(NOW)
    svc = service(provider, clock=clock)
    svc.get_schedule(CHANNEL)
    clock.now += 10
    svc.get_schedule(CHANNEL, force=True)
    assert provider.calls == 1
    clock.now += module.MIN_MANUAL_REFRESH_SECONDS
    svc.get_schedule(CHANNEL, force=True)
    assert provider.calls == 2


def test_other_errors_are_not_remembered():
    provider = FakeProvider(error=NetworkError("x"))
    svc = service(provider)
    svc.get_schedule(CHANNEL)
    svc.get_schedule(CHANNEL)
    assert provider.calls == 2
    provider = FakeProvider(error=HttpStatusError(500))
    svc = service(provider)
    svc.get_schedule(CHANNEL)
    svc.get_schedule(CHANNEL)
    assert provider.calls == 2


def test_success_clears_the_memory_of_a_missing_file():
    provider = FakeProvider(error=HttpStatusError(404))
    clock = Clock(NOW)
    svc = service(provider, clock=clock)
    svc.get_schedule(CHANNEL)
    provider.error = None
    provider.programmes = list(DAY)
    clock.now += module.MIN_MANUAL_REFRESH_SECONDS + 1
    assert svc.get_schedule(CHANNEL, force=True).status == ScheduleStatus.OK
    assert svc._missing == {}
