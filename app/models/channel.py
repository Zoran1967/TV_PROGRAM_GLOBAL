"""Modeli TV stanice i rezultata pretrage."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Channel:
    id: int
    catalog_id: str
    name: str
    country_code: str
    country_name: str
    network: Optional[str] = None


@dataclass(frozen=True)
class SearchResult:
    channel: Channel
    matched_alias: str
    # True kada postoji jos jedna stanica sa istim nazivom u istoj drzavi
    needs_id: bool = False
