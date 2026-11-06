"""Pravljenje servisa aplikacije (katalog, pretraga, raspored)."""

import logging

from app.database.catalog import CatalogDatabase, CatalogError
from app.providers.registry import ProviderRegistry, load_registry
from app.services.schedule_service import ScheduleService
from app.services.search_service import ChannelSearchService

LOGGER = logging.getLogger(__name__)


def create_services():
    """Vraca (servis pretrage, servis rasporeda). Oba su None ako katalog ne radi."""
    try:
        catalog = CatalogDatabase()
    except CatalogError as error:
        LOGGER.error("Katalog stanica nije dostupan: %s", error)
        return None, None
    try:
        registry = load_registry()
    except (OSError, ValueError, KeyError) as error:
        LOGGER.error("Izvori rasporeda nisu ucitani: %s", error)
        registry = ProviderRegistry()
    return ChannelSearchService(catalog), ScheduleService(catalog, registry)
