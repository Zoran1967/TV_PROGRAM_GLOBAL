"""Podesavanja aplikacije: dozvoljene vrednosti, cuvanje i podrazumevane vrednosti.

Ne koristi Kivy. Ako trajno cuvanje ne radi (store je None ili baza prijavi gresku),
podesavanja vaze do zatvaranja aplikacije, a pozivalac dobija "nije sacuvano".
"""

import logging
from typing import NamedTuple, Tuple

LOGGER = logging.getLogger(__name__)


class SettingDef(NamedTuple):
    key: str
    default: str
    options: Tuple[str, ...]


LANGUAGE = "language"
THEME = "theme"
TIME_FORMAT = "time_format"
TIME_ZONE = "time_zone"
REFRESH = "refresh"

# Redosled je i redosled na ekranu Podesavanja
DEFINITIONS = (
    SettingDef(LANGUAGE, "sr", ("sr", "en")),
    SettingDef(THEME, "dark", ("dark", "light")),
    SettingDef(TIME_FORMAT, "24h", ("24h", "12h")),
    SettingDef(TIME_ZONE, "station", ("station", "device")),
    # "source": prema roku izvora; "12h"/"24h": redje od izvora; "manual": samo dugme Osvezi
    SettingDef(REFRESH, "source", ("source", "12h", "24h", "manual")),
)
_BY_KEY = {item.key: item for item in DEFINITIONS}

# Kljuc teksta (app/strings.py) za naziv opcije: "<prefiks><vrednost>", npr. "theme_dark"
_OPTION_PREFIX = {
    LANGUAGE: "lang_",
    THEME: "theme_",
    TIME_FORMAT: "time_format_",
    TIME_ZONE: "time_zone_",
    REFRESH: "refresh_",
}


def option_label_key(setting_key, value):
    return _OPTION_PREFIX[setting_key] + value


REFRESH_SECONDS = {"source": None, "12h": 12 * 3600, "24h": 24 * 3600, "manual": None}


def refresh_policy(value):
    """(najkraci razmak u sekundama ili None, samo_rucno) za vrednost podesavanja osvezavanja."""
    return REFRESH_SECONDS.get(value), value == "manual"


class SettingsService:
    def __init__(self, store=None):
        self._store = store
        self._values = {item.key: item.default for item in DEFINITIONS}
        if store is not None:
            self._load()

    @property
    def persistent(self):
        """True ako postoji trajno cuvanje (da li je upis uspeo, javlja set())."""
        return self._store is not None

    def _load(self):
        try:
            saved = self._store.load_settings()
        except Exception as error:  # greska baze ne sme da sruši aplikaciju
            LOGGER.warning("Podesavanja nisu procitana: %s", error)
            return
        for key, value in saved.items():
            definition = _BY_KEY.get(key)
            if definition is None:
                continue  # nepoznat kljuc (npr. iz novije verzije aplikacije)
            if value in definition.options:
                self._values[key] = value
            else:
                LOGGER.warning("Podesavanje %s ima nedozvoljenu vrednost %r; koristi se podrazumevana", key, value)

    def get(self, key):
        return self._values[key]

    def all(self):
        return dict(self._values)

    @staticmethod
    def definition(key):
        return _BY_KEY[key]

    def set(self, key, value):
        """Menja podesavanje. Baca ValueError za nepoznat kljuc ili nedozvoljenu vrednost.

        Vraca True ako je vrednost i trajno sacuvana, False ako vazi samo u ovoj sesiji.
        """
        definition = _BY_KEY.get(key)
        if definition is None:
            raise ValueError("nepoznato podesavanje: %r" % (key,))
        if value not in definition.options:
            raise ValueError("nedozvoljena vrednost %r za %s" % (value, key))
        self._values[key] = value
        if self._store is None:
            return False
        try:
            self._store.save_setting(key, value)
        except Exception as error:
            LOGGER.warning("Podesavanje %s nije sacuvano: %s", key, error)
            return False
        return True
