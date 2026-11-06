"""Citanje XMLTV rasporeda.

Vreme u XMLTV fajlu moze imati pomak (npr. "20261106193000 +0100") ili biti
"plutajuce" (bez pomaka, npr. "20261106193000"). Plutajuce vreme se tumaci kao
lokalno vreme u zadatoj IANA zoni; bez zone se ne nagadja nego se prijavljuje greska.
"""

import datetime
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional
from zoneinfo import ZoneInfo

from app.models.schedule import Programme
from app.providers.errors import (
    EmptyResponseError,
    EmptyScheduleError,
    ParseError,
    ZoneUnavailableError,
)

LOGGER = logging.getLogger(__name__)

_TIME_RE = re.compile(
    r"^\s*(\d{4})(\d{2})(\d{2})(?:(\d{2})(\d{2})?(\d{2})?)?\s*"
    r"(?:(Z)|([+-])(\d{2}):?(\d{2}))?\s*$"
)


class TimeFormatError(ValueError):
    """Vreme nije u XMLTV obliku."""


@dataclass(frozen=True)
class ParseStats:
    total: int = 0
    kept: int = 0
    other_channel: int = 0
    no_title: int = 0
    bad_time: int = 0
    duplicates: int = 0


@dataclass(frozen=True)
class ParsedSchedule:
    programmes: List[Programme]
    stats: ParseStats


def load_zone(name):
    """Vraca ZoneInfo ili baca ZoneUnavailableError (nepoznata zona ili nema tzdata)."""
    if not name:
        raise ZoneUnavailableError("Vremenska zona stanice nije poznata")
    try:
        return ZoneInfo(name)
    except Exception as error:  # ZoneInfoNotFoundError, ValueError, OSError
        raise ZoneUnavailableError("Zona %r nije dostupna: %s" % (name, error))


def parse_time(text, zone=None, fold=0):
    """Vraca (UTC sekunde, plutajuce). Baca TimeFormatError ili ZoneUnavailableError."""
    match = _TIME_RE.match(text or "")
    if not match:
        raise TimeFormatError("Neispravno vreme: %r" % text)
    year, month, day, hour, minute, second, zulu, sign, off_h, off_m = match.groups()
    try:
        naive = datetime.datetime(
            int(year), int(month), int(day),
            int(hour or 0), int(minute or 0), int(second or 0),
        )
    except ValueError as error:
        raise TimeFormatError("Neispravno vreme %r: %s" % (text, error))
    if zulu or sign:
        offset = datetime.timedelta(hours=int(off_h or 0), minutes=int(off_m or 0))
        if sign == "-":
            offset = -offset
        aware = naive.replace(tzinfo=datetime.timezone(offset))
        return int(aware.timestamp()), False
    if zone is None:
        raise ZoneUnavailableError("Vreme bez pomaka, a zona stanice nije poznata")
    aware = naive.replace(tzinfo=zone, fold=fold)
    return int(aware.timestamp()), True


def _text(node, tag):
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    value = " ".join(child.text.split())
    return value or None


def _resolve_time(text, zone, not_before=None):
    """Vreme, a pri promeni na zimsko racunanje (dvaput isti sat) bira ono koje ne ide unazad."""
    value, floating = parse_time(text, zone, fold=0)
    fold = 0
    if floating and not_before is not None and value < not_before:
        alternative, _ = parse_time(text, zone, fold=1)
        if alternative >= not_before:
            value, fold = alternative, 1
    return value, floating, fold


def parse_xmltv(data, channel_id, zone=None):
    """Cita XMLTV i vraca ParsedSchedule za jednu stanicu.

    Baca EmptyResponseError, ParseError, EmptyScheduleError ili ZoneUnavailableError.
    """
    if not data or not data.strip():
        raise EmptyResponseError("Prazan odgovor")
    if b"<!ENTITY" in data:
        raise ParseError("XML sa definicijom entiteta nije dozvoljen")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ParseError("Neispravan XML: %s" % error)
    if root.tag != "tv":
        raise ParseError("Nije XMLTV (koren je <%s>)" % root.tag)

    wanted = channel_id.casefold()
    total = other = no_title = bad_time = duplicates = 0
    programmes = []
    seen = set()
    previous_start = None
    for node in root.iter("programme"):
        total += 1
        if (node.get("channel") or "").casefold() != wanted:
            other += 1
            continue
        title = _text(node, "title")
        if not title:
            no_title += 1
            continue
        try:
            start, floating, fold = _resolve_time(node.get("start"), zone, previous_start)
            end = None
            if node.get("stop"):
                end, _, _ = _resolve_time(node.get("stop"), zone, start)
                if end < start:
                    end = None
        except TimeFormatError:
            bad_time += 1
            continue
        key = (start, title)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        previous_start = start
        programmes.append(
            Programme(
                title=title,
                start_utc=start,
                end_utc=end,
                description=_text(node, "desc"),
                category=_text(node, "category"),
            )
        )

    programmes.sort(key=lambda item: item.start_utc)
    stats = ParseStats(total, len(programmes), other, no_title, bad_time, duplicates)
    if not programmes:
        raise EmptyScheduleError(
            "Nema emisija za %s (u fajlu: %d, tudji kanal: %d, bez naslova: %d, lose vreme: %d)"
            % (channel_id, total, other, no_title, bad_time)
        )
    return ParsedSchedule(programmes, stats)
