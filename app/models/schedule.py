"""Modeli rasporeda."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChannelSource:
    """Veza stanice sa izvorom rasporeda (red iz tabele channel_source)."""

    source_id: str
    source_channel_id: str
    timezone: Optional[str]
    days_available: Optional[int]
    priority: int = 0


@dataclass(frozen=True)
class Programme:
    """Jedna emisija. Vremena su UTC sekunde; polja koja izvor ne daje ostaju None."""

    title: str
    start_utc: int
    end_utc: Optional[int] = None
    description: Optional[str] = None
    category: Optional[str] = None
