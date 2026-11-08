"""Pravljenje servisa aplikacije (katalog, pretraga, raspored, omiljene, podesavanja)."""

import logging
from typing import NamedTuple, Optional

from app.database.catalog import CatalogDatabase, CatalogError
from app.database.userdata import UserDatabase, UserDataError
from app.providers.registry import ProviderRegistry, load_registry
from app.services.favourites_service import FavouritesService
from app.services.schedule_service import ScheduleService
from app.services.search_service import ChannelSearchService
from app.services.settings_service import SettingsService

LOGGER = logging.getLogger(__name__)

# Stanje trajnog cuvanja (ekran Podesavanja ga prevodi na jezik interfejsa)
STORAGE_ON = "on"
STORAGE_MEMORY = "memory"  # nije podeseno: sve vazi samo do zatvaranja aplikacije
STORAGE_UNAVAILABLE = "unavailable"


class Services(NamedTuple):
    search: Optional[ChannelSearchService] = None
    schedule: Optional[ScheduleService] = None
    favourites: Optional[FavouritesService] = None
    # Podesavanja rade uvek (bez trajnog cuvanja vaze do zatvaranja aplikacije)
    settings: SettingsService = None
    storage_state: str = STORAGE_UNAVAILABLE
    storage_detail: str = ""


def _open_store(user_data_dir):
    if not user_data_dir:
        return None, STORAGE_MEMORY, ""
    try:
        return UserDatabase(UserDatabase.default_path(user_data_dir)), STORAGE_ON, ""
    except UserDataError as error:
        LOGGER.error("Trajno cuvanje nije dostupno: %s", error)
        return None, STORAGE_UNAVAILABLE, str(error)


def create_services(user_data_dir=None):
    """Pravi sve servise. Bez kataloga nema pretrage ni rasporeda; bez korisnicke baze nema
    omiljenih ni trajnog kesa ni trajnih podesavanja, ali pretraga i raspored rade."""
    store, storage_state, storage_detail = _open_store(user_data_dir)
    settings = SettingsService(store)
    try:
        catalog = CatalogDatabase()
    except CatalogError as error:
        LOGGER.error("Katalog stanica nije dostupan: %s", error)
        return Services(settings=settings, storage_state=storage_state,
                        storage_detail=storage_detail)
    try:
        registry = load_registry()
    except (OSError, ValueError, KeyError) as error:
        LOGGER.error("Izvori rasporeda nisu ucitani: %s", error)
        registry = ProviderRegistry()

    favourites = FavouritesService(catalog, store) if store is not None else None
    return Services(
        search=ChannelSearchService(catalog),
        schedule=ScheduleService(catalog, registry, store=store),
        favourites=favourites,
        settings=settings,
        storage_state=storage_state,
        storage_detail=storage_detail,
    )
