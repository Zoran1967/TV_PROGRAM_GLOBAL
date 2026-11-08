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


# Ogranicenja duzine polja: pokvaren ili zlonameran fajl ne sme da napravi ogromnu stavku na ekranu
MAX_TITLE = 300
MAX_DESCRIPTION = 3000
MAX_CATEGORY = 100
MAX_SUBTITLE = 300
MAX_PERSON = 100
MAX_PEOPLE = 12
MAX_LIST_ITEMS = 6
MAX_SMALL = 60

_ONSCREEN_RE = re.compile(r"[sS]\s*(\d{1,3})\s*[eE]\s*(\d{1,4})|(\d{1,2})\s*[xX]\s*(\d{1,4})")
_NS_PART_RE = re.compile(r"^\s*(\d{1,5})?\s*(?:/\s*(\d{1,5}))?\s*$")


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


def _text(node, tag, limit):
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    value = " ".join(child.text.split())
    if len(value) > limit:
        value = value[:limit - 3].rstrip() + "..."
    return value or None


def _texts(node, tag, limit, max_items):
    """Svi neprazni tekstovi elemenata <tag> (bez duplikata), ogranicenog broja i duzine."""
    values = []
    for child in node.findall(tag):
        value = " ".join((child.text or "").split())
        if not value:
            continue
        if len(value) > limit:
            value = value[:limit - 3].rstrip() + "..."
        if value not in values:
            values.append(value)
        if len(values) >= max_items:
            break
    return tuple(values)


def _credits(node, tag):
    box = node.find("credits")
    if box is None:
        return ()
    return _texts(box, tag, MAX_PERSON, MAX_PEOPLE)


def _year(node):
    child = node.find("date")
    text = (child.text or "").strip() if child is not None else ""
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        if 1850 <= year <= 2100:
            return year
    return None


def _age_rating(node):
    value = node.find("rating/value")
    if value is None or not (value.text or "").strip():
        return None
    return " ".join(value.text.split())[:MAX_SMALL]


def _number(text):
    return int(text) if text and text.isdigit() else None


def parse_episode_numbers(node):
    """(sezona, epizoda, ukupno epizoda); polja koja izvor ne daje su None.

    Podrzava xmltv_ns (\"1.4.0/1\": brojanje od nule) i onscreen (\"S02E05\", \"2x05\").
    """
    onscreen = None
    for child in node.findall("episode-num"):
        text = " ".join((child.text or "").split())
        system = (child.get("system") or "").lower()
        if system == "xmltv_ns":
            parts = text.split(".")
            if len(parts) >= 2:
                season_part, episode_part = parts[0], parts[1]
                season_match = _NS_PART_RE.match(season_part)
                episode_match = _NS_PART_RE.match(episode_part)
                if season_match and episode_match:
                    season = _number(season_match.group(1))
                    episode = _number(episode_match.group(1))
                    total = _number(episode_match.group(2))
                    if season is not None or episode is not None:
                        return (
                            season + 1 if season is not None else None,
                            episode + 1 if episode is not None else None,
                            total,
                        )
        elif onscreen is None:
            match = _ONSCREEN_RE.search(text)
            if match:
                season = match.group(1) or match.group(3)
                episode = match.group(2) or match.group(4)
                onscreen = (int(season), int(episode), None)
    return onscreen if onscreen is not None else (None, None, None)


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
    # Provera i za UTF-16 (znaci razdvojeni nulama) i za mala/velika slova
    if b"<!entity" in data.replace(b"\x00", b"").lower():
        raise ParseError("XML sa definicijom entiteta nije dozvoljen")
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, LookupError, ValueError) as error:  # LookupError: nepoznato kodiranje
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
        title = _text(node, "title", MAX_TITLE)
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
        season, episode, episode_total = parse_episode_numbers(node)
        genres = _texts(node, "category", MAX_CATEGORY, MAX_LIST_ITEMS)
        programmes.append(
            Programme(
                title=title,
                start_utc=start,
                end_utc=end,
                description=_text(node, "desc", MAX_DESCRIPTION),
                category=_text(node, "category", MAX_CATEGORY),
                subtitle=_text(node, "sub-title", MAX_SUBTITLE),
                season=season,
                episode=episode,
                episode_total=episode_total,
                year=_year(node),
                age_rating=_age_rating(node),
                genres=genres,
                countries=_texts(node, "country", MAX_SMALL, MAX_LIST_ITEMS),
                directors=_credits(node, "director"),
                actors=_credits(node, "actor"),
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
