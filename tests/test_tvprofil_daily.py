"""Rezerva TvProfila: kad nedeljni fajl vrati 404, raspored se sklapa iz dnevnih fajlova."""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.models.schedule import ChannelSource  # noqa: E402
from app.providers.base import ProviderInfo  # noqa: E402
from app.providers.errors import HttpStatusError, NetworkError  # noqa: E402
from app.providers.tvprofil import TvProfilProvider  # noqa: E402

WEEKLY = "https://example.invalid/{id}/weekly_{id}.xml"
DAILY = "https://example.invalid/{id}/{date}_{id}.xml"
INFO = ProviderInfo("tvprofil", "TvProfil", "pending", "Izvor: test", "https://example.invalid", 3600)


def xml(*programmes):
    body = "".join(
        '<programme start="%s" channel="rts1.sr"><title>%s</title></programme>' % item
        for item in programmes
    )
    return ('<?xml version="1.0"?><tv>%s</tv>' % body).encode()


def source():
    return ChannelSource("tvprofil", "rts1.sr", "Europe/Belgrade", 7, 0)


def now():
    return datetime(2026, 11, 8, 23, 30, tzinfo=ZoneInfo("Europe/Belgrade"))


def make(routes, daily=DAILY):
    calls = []

    def fetcher(url, timeout):
        calls.append(url)
        result = routes.get(url, HttpStatusError(404))
        if isinstance(result, Exception):
            raise result
        return result

    provider = TvProfilProvider(INFO, WEEKLY, fetcher=fetcher, daily_url_template=daily, now=now)
    return provider, calls


def test_weekly_file_is_used_when_it_exists():
    provider, calls = make({"https://example.invalid/rts1.sr/weekly_rts1.sr.xml":
                            xml(("20261108190000", "A"))})
    assert [p.title for p in provider.fetch_programmes(source())] == ["A"]
    assert len(calls) == 1


def test_daily_files_are_used_when_weekly_is_404():
    provider, calls = make({
        "https://example.invalid/rts1.sr/2026-11-08_rts1.sr.xml": xml(("20261108190000", "Danas")),
        "https://example.invalid/rts1.sr/2026-11-09_rts1.sr.xml": xml(("20261109190000", "Sutra")),
    })
    assert [p.title for p in provider.fetch_programmes(source())] == ["Danas", "Sutra"]
    assert calls[0].endswith("weekly_rts1.sr.xml")


def test_missing_second_day_is_not_an_error():
    provider, _ = make({
        "https://example.invalid/rts1.sr/2026-11-08_rts1.sr.xml": xml(("20261108190000", "Danas")),
    })
    assert [p.title for p in provider.fetch_programmes(source())] == ["Danas"]


def test_original_404_is_raised_when_nothing_exists():
    provider, _ = make({})
    with pytest.raises(HttpStatusError) as info:
        provider.fetch_programmes(source())
    assert info.value.status == 404


def test_no_fallback_without_template_or_for_other_errors():
    provider, calls = make({}, daily=None)
    with pytest.raises(HttpStatusError):
        provider.fetch_programmes(source())
    assert len(calls) == 1
    provider, calls = make({"https://example.invalid/rts1.sr/weekly_rts1.sr.xml": NetworkError("x")})
    with pytest.raises(NetworkError):
        provider.fetch_programmes(source())
    assert len(calls) == 1
