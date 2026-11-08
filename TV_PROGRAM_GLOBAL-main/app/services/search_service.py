"""Pretraga TV stanica po nazivu, skracenici i alternativnom nazivu."""

import logging
import sqlite3
from dataclasses import dataclass
from enum import Enum

from app.database.catalog import CatalogDatabase
from app.models.channel import SearchResult
from app.utils.text import clean_query, normalize_key

DEFAULT_LIMIT = 50
MIN_KEY_LENGTH = 2

_LOGGER = logging.getLogger(__name__)


class SearchStatus(Enum):
    OK = "ok"
    EMPTY_QUERY = "empty_query"
    TOO_SHORT = "too_short"
    NOT_FOUND = "not_found"
    CATALOG_ERROR = "catalog_error"


@dataclass(frozen=True)
class SearchOutcome:
    status: SearchStatus
    results: tuple = ()
    truncated: bool = False


class ChannelSearchService:
    def __init__(self, catalog, limit=DEFAULT_LIMIT):
        self._catalog = catalog
        self._limit = limit

    def catalog_summary(self):
        """Kratak opis kataloga za prikaz u podesavanjima."""
        meta = self._catalog.meta()
        return {
            "channels": self._catalog.channel_count(),
            "source_commit": meta.get("source_commit", "nepoznat"),
            "built_at": meta.get("built_at", "nepoznato"),
            "license": meta.get("license", "nepoznata"),
        }

    def search(self, query):
        key = normalize_key(clean_query(query))
        if not key:
            return SearchOutcome(SearchStatus.EMPTY_QUERY)
        if len(key) < MIN_KEY_LENGTH:
            return SearchOutcome(SearchStatus.TOO_SHORT)
        try:
            matches = self._catalog.find(key, self._limit)
        except sqlite3.Error:
            _LOGGER.exception("Pretraga kataloga nije uspela")
            return SearchOutcome(SearchStatus.CATALOG_ERROR)
        if not matches.items:
            return SearchOutcome(SearchStatus.NOT_FOUND)
        return SearchOutcome(
            SearchStatus.OK, _build_results(matches.items), matches.truncated
        )


def _build_results(items):
    counts = {}
    for channel, _alias in items:
        identity = (channel.name.casefold(), channel.country_code)
        counts[identity] = counts.get(identity, 0) + 1
    return tuple(
        SearchResult(
            channel=channel,
            matched_alias=alias,
            needs_id=counts[(channel.name.casefold(), channel.country_code)] > 1,
        )
        for channel, alias in items
    )


def create_default_service():
    """Otvara ugradjeni katalog. Baca CatalogError ako ne moze."""
    return ChannelSearchService(CatalogDatabase())
