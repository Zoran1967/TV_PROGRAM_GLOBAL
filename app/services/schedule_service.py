"""Raspored jedne stanice za danas, u vremenskoj zoni stanice.

Servis ne koristi Kivy i ne dira UI. get_schedule() blokira dok traje mrezni
zahtev, pa ga UI poziva iz pozadinske niti. refresh_view() nikad ne koristi mrezu:
samo ponovo racuna prikaz (Sada/Sledece, promena dana) iz vec preuzetih podataka.
Baza kataloga se cita samo kroz sources_for(), koji treba pozvati iz glavne niti.
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
from app.services.now_next import compute_now_next

LOGGER = logging.getLogger(__name__)

MAX_CACHE_ENTRIES = 50
# Rucno osvezavanje ranije od ovoga koristi vec preuzete podatke (da se izvor ne opterecuje)
MIN_MANUAL_REFRESH_SECONDS = 60
# Rupa u rasporedu se prijavljuje tek kad je duza od ovoga
MIN_GAP_SECONDS = 120
# Sacuvan raspored "iz buducnosti" za vise od ovoga (pogresan sat) se ne koristi
MAX_CLOCK_SKEW_SECONDS = 300


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
    is_current: bool = False
    is_next: bool = False
    is_past: bool = False
    # Ako posle ove emisije u rasporedu ima rupe, vreme kada se rupa zavrsava
    # (pocinje u end)
    gap_until: Optional[datetime.datetime] = None


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
    now_local: Optional[datetime.datetime] = None
    entries: Tuple[ScheduleEntry, ...] = field(default_factory=tuple)
    # "Sada" i "Sledece" (racunato nad celim rasporedom, "Sledece" moze biti sutra)
    current: Optional[ScheduleEntry] = None
    current_end: Optional[datetime.datetime] = None
    current_end_derived: bool = False
    progress: Optional[float] = None
    next: Optional[ScheduleEntry] = None
    fetched_at: Optional[int] = None
    refresh_seconds: int = 0
    # Prikazani su stariji podaci jer osvezavanje nije uspelo
    stale: bool = False
    error_status: Optional[ScheduleStatus] = None
    http_status: Optional[int] = None
    detail: str = ""


@dataclass
class _CacheEntry:
    fetched_at: int
    programmes: list
    # (status, http_status, tekst) poslednjeg neuspelog osvezavanja; None ako je uspelo
    error: Optional[tuple] = None


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
    def __init__(self, catalog, registry, clock=time.time, store=None):
        self._catalog = catalog
        self._registry = registry
        self._clock = clock
        # Trajni kes (UserDatabase) ili None: tada se podaci cuvaju samo u memoriji
        self._store = store
        self._cache = {}  # (source_id, source_channel_id) -> _CacheEntry
        self._lock = threading.Lock()

    def provider_summary(self):
        """[(id izvora, status licence)] za izvore koji su ucitani u ovoj izgradnji."""
        return [(source_id, self._registry.get(source_id).info.license_status)
                for source_id in self._registry.ids()]

    def sources_for(self, channel):
        """Izvori za stanicu iz kataloga (pozivati iz glavne niti)."""
        return self._catalog.sources_for(channel.id)

    def get_schedule(self, channel, sources=None, force=False):
        """Vraca raspored; po potrebi preuzima podatke (blokira)."""
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

    def refresh_view(self, channel, sources):
        """Ponovo racuna prikaz iz vec preuzetih podataka (bez mreze).

        Vraca None ako za stanicu nema nista u kesu.
        """
        for source in sources or ():
            provider = self._registry.get(source.source_id)
            cached = self._cache_get((source.source_id, source.source_channel_id))
            if provider is None or cached is None:
                continue
            try:
                zone = load_zone(source.timezone)
            except ZoneUnavailableError:
                continue
            return self._build(provider, channel, source, zone, cached, int(self._clock()))
        return None

    # ------------------------------------------------------------------

    def _base(self, provider, channel, source):
        info = provider.info
        return dict(
            channel=channel, source_name=info.name, attribution=info.attribution_text,
            license_status=info.license_status, timezone=source.timezone or "",
            refresh_seconds=info.min_refresh_seconds,
        )

    def _load_from(self, provider, channel, source, force):
        info = provider.info
        base = self._base(provider, channel, source)
        try:
            zone = load_zone(source.timezone)
        except ZoneUnavailableError as error:
            return ScheduleOutcome(ScheduleStatus.ZONE_UNAVAILABLE, detail=str(error), **base)

        key = (source.source_id, source.source_channel_id)
        now = int(self._clock())
        cached = self._cache_get(key)
        age = now - cached.fetched_at if cached else None
        if cached and cached.error is None and age < (
                MIN_MANUAL_REFRESH_SECONDS if force else info.min_refresh_seconds):
            entry = cached  # svez kes (ili tek osvezeno rucno): bez mreze
        else:
            try:
                # Adapter bi trebalo da vrati sortirano; ovde se to jos jednom obezbedjuje
                programmes = sorted(provider.fetch_programmes(source),
                                    key=lambda item: item.start_utc)
                entry = _CacheEntry(now, programmes)
                self._cache_put(key, entry)
                self._persist(source, entry)
            except ProviderError as error:
                LOGGER.warning("Izvor %s, stanica %s: %s (%s)", info.id,
                               source.source_channel_id, error.code, error)
                status = _status_for(error)
                http_status = getattr(error, "status", None)
                if not cached:
                    return ScheduleOutcome(status, detail=str(error), http_status=http_status, **base)
                entry = _CacheEntry(cached.fetched_at, cached.programmes,
                                    (status, http_status, str(error)))
                self._cache_put(key, entry)
            except Exception as error:  # neocekivana greska adaptera ne sme da sruši aplikaciju
                LOGGER.exception("Neocekivana greska izvora %s", info.id)
                return ScheduleOutcome(ScheduleStatus.ERROR, detail=str(error), **base)
        return self._build(provider, channel, source, zone, entry, now)

    def _build(self, provider, channel, source, zone, entry, now):
        base = self._base(provider, channel, source)
        programmes = entry.programmes
        local_now = datetime.datetime.fromtimestamp(now, zone)
        today = local_now.date()
        common = dict(base, local_date=today, now_local=local_now,
                      zone_label=local_now.tzname() or "", fetched_at=entry.fetched_at)
        if entry.error:
            common.update(stale=True, error_status=entry.error[0],
                          http_status=entry.error[1], detail=entry.error[2])

        state = compute_now_next(programmes, now)

        def to_local(timestamp):
            return datetime.datetime.fromtimestamp(timestamp, zone) if timestamp is not None else None

        def entry_for(item, **flags):
            return ScheduleEntry(
                start=to_local(item.start_utc), end=to_local(item.end_utc),
                title=item.title, description=item.description, category=item.category, **flags)

        entries = self._entries_for_today(programmes, zone, now, today, state, entry_for)
        extra = {}
        if state.current is not None:
            extra.update(
                current=entry_for(state.current, is_current=True),
                current_end=to_local(state.current_end_utc),
                current_end_derived=state.current_end_derived,
                progress=state.progress)
        if state.next is not None:
            extra["next"] = entry_for(state.next, is_next=True)
        if not entries:
            return ScheduleOutcome(ScheduleStatus.NO_DATA_FOR_DATE, **common, **extra)
        return ScheduleOutcome(ScheduleStatus.OK, entries=entries, **common, **extra)

    @staticmethod
    def _entries_for_today(programmes, zone, now, today, state, entry_for):
        day_start = datetime.datetime.combine(today, datetime.time.min, tzinfo=zone)
        day_end = datetime.datetime.combine(
            today + datetime.timedelta(days=1), datetime.time.min, tzinfo=zone
        )
        start_utc, end_utc = int(day_start.timestamp()), int(day_end.timestamp())
        selected = []
        for index, item in enumerate(programmes):
            if item.end_utc is not None:
                overlaps = item.start_utc < end_utc and item.end_utc > start_utc
            else:
                overlaps = start_utc <= item.start_utc < end_utc
            if overlaps:
                selected.append((index, item))

        entries = []
        for index, item in selected:
            following = programmes[index + 1] if index + 1 < len(programmes) else None
            effective_end = item.end_utc
            if effective_end is None and following is not None:
                effective_end = following.start_utc
            gap_until = None
            if item.end_utc is not None and following is not None:
                if following.start_utc - item.end_utc >= MIN_GAP_SECONDS:
                    gap_until = datetime.datetime.fromtimestamp(following.start_utc, zone)
            entries.append(entry_for(
                item,
                is_current=state.current is item,
                is_next=state.next is item,
                is_past=effective_end is not None and effective_end <= now,
                gap_until=gap_until,
            ))
        return tuple(entries)

    def _cache_get(self, key):
        with self._lock:
            entry = self._cache.get(key)
        if entry is not None or self._store is None:
            return entry
        return self._restore(key)

    def _restore(self, key):
        """Ucitava poslednji sacuvan raspored sa diska (posle ponovnog pokretanja aplikacije)."""
        try:
            saved = self._store.load_schedule(*key)
        except Exception as error:  # kes na disku nikad ne sme da sruši prikaz
            LOGGER.warning("Sacuvan raspored %s nije procitan: %s", key, error)
            return None
        if saved is None:
            return None
        fetched_at, programmes = saved
        if fetched_at > int(self._clock()) + MAX_CLOCK_SKEW_SECONDS:
            LOGGER.warning("Sacuvan raspored %s je iz buducnosti (sat telefona?); ignorise se", key)
            return None
        entry = _CacheEntry(fetched_at, programmes)
        with self._lock:
            # Ako je u medjuvremenu stigao noviji podatak u memoriju, on ima prednost
            existing = self._cache.get(key)
            if existing is not None:
                return existing
        self._cache_put(key, entry)
        return entry

    def _persist(self, source, entry):
        if self._store is None:
            return
        try:
            self._store.save_schedule(
                source.source_id, source.source_channel_id, entry.fetched_at, entry.programmes)
        except Exception as error:  # nema trajnog cuvanja, ali prikaz radi dalje
            LOGGER.warning("Raspored %s nije sacuvan na disk: %s", source.source_channel_id, error)

    def _cache_put(self, key, entry):
        with self._lock:
            self._cache[key] = entry
            while len(self._cache) > MAX_CACHE_ENTRIES:
                oldest = min(self._cache, key=lambda k: self._cache[k].fetched_at)
                del self._cache[oldest]
