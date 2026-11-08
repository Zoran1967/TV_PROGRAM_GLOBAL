"""Omiljene stanice: cuvanje u korisnickoj bazi i pretvaranje u stanice iz kataloga.

Ne koristi Kivy. Katalog je vezan za glavnu nit, pa se servis poziva samo iz nje.
"""

import logging
from dataclasses import dataclass
from typing import Tuple

from app.models.channel import Channel

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FavouritesList:
    channels: Tuple[Channel, ...] = ()
    # Omiljene koje vise nisu u katalogu (ostaju sacuvane, ali se ne prikazuju)
    missing: int = 0


class FavouritesService:
    def __init__(self, catalog, store):
        self._catalog = catalog
        self._store = store

    def is_favourite(self, channel):
        return self._store.is_favourite(channel.catalog_id)

    def set_favourite(self, channel, value):
        if value:
            self._store.add_favourite(channel.catalog_id)
        else:
            self._store.remove_favourite(channel.catalog_id)
        return value

    def toggle(self, channel):
        """Menja stanje i vraca novo (True = sada je omiljena)."""
        return self.set_favourite(channel, not self.is_favourite(channel))

    def list_channels(self):
        channels = []
        missing = 0
        for catalog_id in self._store.favourite_ids():
            channel = self._catalog.get_by_catalog_id(catalog_id)
            if channel is None:
                LOGGER.warning("Omiljena stanica %s nije u katalogu", catalog_id)
                missing += 1
            else:
                channels.append(channel)
        channels.sort(key=lambda item: (item.name.casefold(), item.country_name, item.catalog_id))
        return FavouritesList(tuple(channels), missing)
