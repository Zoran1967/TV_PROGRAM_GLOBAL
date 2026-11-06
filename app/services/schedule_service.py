"""Raspored jedne stanice za danas, u vremenskoj zoni stanice.

Servis ne koristi Kivy i ne dira UI. get_schedule() blokira dok traje mrezni
zahtev, pa ga UI poziva iz pozadinske niti. Baza kataloga se cita samo kroz
sources_for(), koji treba pozvati iz glavne niti (isti kao pretraga).
"""

import datetime
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from app.models.channel import Channel
from app.providers.errors import (
    EmptyResponseError,
    EmptyScheduleError,
    HttpStatusError,
    InvalidSourceError,
    NetworkError,
    ParseError,
    ProviderError,
    RateLimitedError,
    ResponseTooLargeError,
    ZoneUnavailableError,
)
from app.providers.xmltv import load_zone

LOGGER = logging.getLogger(__name__)

MAX_CACHE_ENTRIES = 50


class ScheduleStatus(Enum):
    OK = "ok"
    NO_SOURCE = "no_source"
    SOURCE_UNAVAILABLE = "source_unavailable"
    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"
    RATE_LIMITED = "rate_limited"
    EMPTY = "empty"
    PARSE_ERROR = "parse_error"
    ZONE_UNAVAILABLE = "zone_unavailable"
    NO_DATA_FOR_DATE = "no_data_for_date"
    ERROR = "error"


@dataclass(frozen=True)
class ScheduleEntry:
    start: datetime.datetime  # lokalno vreme stanice (sa zonom)
    end: Optional[datetime.datetime]
    title: str
    description: Optional[str] = None
    category: Optional[str] = None


@dataclass(frozen=True)
class ScheduleOutcome:
    status: ScheduleStatus
    channel: Channel
    source_name: str = ""
    attribution: str = ""
    license_status: str = ""
    timezone: str = ""
    zone_label: str = ""
    local_date: Optional[datetime.date] = None
    entries: Tuple[ScheduleEntry, ...] = field(default_factory=tuple)
    fetched_at: Optional[int] = None
    # Prikazani su stariji podaci jer osvezavanje nije uspelo
    stale: bool = False
    error_status: Optional[ScheduleStatus] = None
    http_status: Optional[int] = None
    detail: str = ""


def _status_for(error):
    if isinstance(error, NetworkError):
        return ScheduleStatus.NETWORK_ERROR
    if isinstance(error, HttpStatusError):
        return ScheduleStatus.HTTP_ERROR
    if isinstance(error, RateLimitedError):
        return ScheduleStatus.RATE_LIMITED
    if isinstance(error, (EmptyResponseError, EmptyScheduleError)):
        return ScheduleStatus.EMPTY
    if isinstance(error, (ParseError, ResponseTooLargeError, InvalidSourceError)):
        return ScheduleStatus.PARSE_ERROR
    if isinstance(error, ZoneUnavailableError):
        return ScheduleStatus.ZONE_UNAVAILABLE
    return ScheduleStatus.ERROR


class ScheduleService:
    def __init__(self, catalog, registry, clock=time.time):
        self._catalog = catalog
        self._registry = registry
        self._clock = clock
        self._cache = {}  # (source_id, source_channel_id) -> (fetched_at, programmes)
        self._lock = threading.Lock()

    def provider_summary(self):
        """[(id izvora, status licence)] za izvore koji su ucitani u ovoj izgradnji."""
        return [(source_id, self._registry.get(source_id).info.license_status)
                for source_id in self._registry.ids()]

    def sources_for(self, channel):
        """Izvori za stanicu iz kataloga (pozivati iz glavne niti)."""
        return self._catalog.sources_for(channel.id)

    def get_schedule(self, channel, sources=None, force=False):
        if sources is None:
            sources = self.sources_for(channel)
        if not sources:
            return ScheduleOutcome(ScheduleStatus.NO_SOURCE, channel)

        first_failure = None
        usable = False
        for source in sources:
            provider = self._registry.get(source.source_id)
            if provider is None:
                continue
            usable = True
            outcome = self._load_from(provider, channel, source, force)
            if outcome.status == ScheduleStatus.OK:
                return outcome
            if first_failure is None:
                first_failure = outcome
        if not usable:
            return ScheduleOutcome(
                ScheduleStatus.SOURCE_UNAVAILABLE, channel,
                detail=", ".join(sorted({s.source_id for s in sources})),
            )
        return first_failure

    # ------------------------------------------------------------------

    def _load_from(self, provider, channel, source, force):
        info = provider.info
        base = dict(
            channel=channel, source_name=info.name, attribution=info.attribution_text,
            license_status=info.license_status, timezone=source.timezone or "",
        )
        try:
            zone = load_zone(source.timezone)
        except ZoneUnavailableError as error:
            return ScheduleOutcome(ScheduleStatus.ZONE_UNAVAILABLE, detail=str(error), **base)

        key = (source.source_id, source.source_channel_id)
        now = int(self._clock())
        cached = self._cache_get(key)
        stale_error = None
        if cached and not force and now - cached[0] < info.min_refresh_seconds:
            fetched_at, programmes = cached
        else:
            try:
                programmes = provider.fetch_programmes(source)
                fetched_at = now
                self._cache_put(key, now, programmes)
            except ProviderError as error:
                LOGGER.warning("Izvor %s, stanica %s: %s (%s)", info.id,
                               source.source_channel_id, error.code, error)
                status = _status_for(error)
                http_status = getattr(error, "status", None)
                if not cached:
                    return ScheduleOutcome(status, detail=str(error), http_status=http_status, **base)
                fetched_at, programmes = cached
                stale_error = (status, http_status, str(error))
            except Exception as error:  # neocekivana greska adaptera ne sme da sruši aplikaciju
                LOGGER.exception("Neocekivana greska izvora %s", info.id)
                return ScheduleOutcome(ScheduleStatus.ERROR, detail=str(error), **base)

        entries, local_date, zone_label = self._entries_for_today(programmes, zone, now)
        common = dict(base, local_date=local_date, zone_label=zone_label, fetched_at=fetched_at)
        if stale_error:
            common.update(stale=True, error_status=stale_error[0],
                          http_status=stale_error[1], detail=stale_error[2])
        if not entries:
            return ScheduleOutcome(ScheduleStatus.NO_DATA_FOR_DATE, **common)
        return ScheduleOutcome(ScheduleStatus.OK, entries=entries, **common)

    @staticmethod
    def _entries_for_today(programmes, zone, now):
        local_now = datetime.datetime.fromtimestamp(now, zone)
        today = local_now.date()
        day_start = datetime.datetime.combine(today, datetime.time.min, tzinfo=zone)
        day_end = datetime.datetime.combine(
            today + datetime.timedelta(days=1), datetime.time.min, tzinfo=zone
        )
        start_utc, end_utc = int(day_start.timestamp()), int(day_end.timestamp())
        entries = []
        for item in programmes:
            if item.end_utc is not None:
                overlaps = item.start_utc < end_utc and item.end_utc > start_utc
            else:
                overlaps = start_utc <= item.start_utc < end_utc
            if not overlaps:
                continue
            entries.append(ScheduleEntry(
                start=datetime.datetime.fromtimestamp(item.start_utc, zone),
                end=(datetime.datetime.fromtimestamp(item.end_utc, zone)
                     if item.end_utc is not None else None),
                title=item.title, description=item.description, category=item.category,
            ))
        return tuple(entries), today, local_now.tzname() or ""

    def _cache_get(self, key):
        with self._lock:
            return self._cache.get(key)

    def _cache_put(self, key, fetched_at, programmes):
        with self._lock:
            self._cache[key] = (fetched_at, programmes)
            while len(self._cache) > MAX_CACHE_ENTRIES:
                oldest = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest]
