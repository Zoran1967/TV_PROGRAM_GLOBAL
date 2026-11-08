"""Pravljenje servisa aplikacije (katalog, pretraga, raspored, omiljene)."""

import logging
from typing import NamedTuple, Optional

from app.database.catalog import CatalogDatabase, CatalogError
from app.database.userdata import UserDatabase, UserDataError
from app.providers.registry import ProviderRegistry, load_registry
from app.services.favourites_service import FavouritesService
from app.services.schedule_service import ScheduleService
from app.services.search_service import ChannelSearchService

LOGGER = logging.getLogger(__name__)


class Services(NamedTuple):
    search: Optional[ChannelSearchService] = None
    schedule: Optional[ScheduleService] = None
    favourites: Optional[FavouritesService] = None
    # Opis stanja trajnog cuvanja, za ekran Podesavanja
    storage_info: str = "nedostupno"


def create_services(user_data_dir=None):
    """Pravi sve servise. Bez kataloga nema nijednog; bez korisnicke baze nema omiljenih
    ni trajnog kesa, ali pretraga i raspored rade (kes je tada samo u memoriji)."""
    try:
        catalog = CatalogDatabase()
    except CatalogError as error:
        LOGGER.error("Katalog stanica nije dostupan: %s", error)
        return Services()
    try:
        registry = load_registry()
    except (OSError, ValueError, KeyError) as error:
        LOGGER.error("Izvori rasporeda nisu ucitani: %s", error)
        registry = ProviderRegistry()

    store = None
    storage_info = "nije podešeno (samo memorija)"
    if user_data_dir:
        try:
            store = UserDatabase(UserDatabase.default_path(user_data_dir))
            storage_info = "uključeno"
        except UserDataError as error:
            LOGGER.error("Trajno cuvanje nije dostupno: %s", error)
            storage_info = "nedostupno (%s)" % error
    favourites = FavouritesService(catalog, store) if store is not None else None
    return Services(
        search=ChannelSearchService(catalog),
        schedule=ScheduleService(catalog, registry, store=store),
        favourites=favourites,
        storage_info=storage_info,
    )
