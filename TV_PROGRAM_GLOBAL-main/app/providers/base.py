"""Ugovor za izvore rasporeda. Svaki izvor je jedan adapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from app.models.schedule import ChannelSource, Programme


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    license_status: str  # "approved" ili "pending"
    attribution_text: str
    attribution_url: str
    min_refresh_seconds: int


class ScheduleProvider(ABC):
    info: ProviderInfo

    @abstractmethod
    def fetch_programmes(self, source: ChannelSource) -> List[Programme]:
        """Preuzima raspored jedne stanice (sve dane koje izvor daje).

        Baca ProviderError (vidi app.providers.errors). Ne sme da menja bazu
        niti UI; vraca samo normalizovane emisije.
        """
