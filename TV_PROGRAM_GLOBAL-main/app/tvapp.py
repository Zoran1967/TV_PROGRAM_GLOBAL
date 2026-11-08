"""Glavna aplikaciona klasa (KivyMD)."""

import logging
import os
import sys
import time
from zoneinfo import ZoneInfo

import kivy
import kivymd
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.logger import Logger
from kivy.properties import (
    DictProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.utils import platform
from kivymd.app import MDApp

from app.build_flavor import FLAVOR
from app.screens.favourites_view import FavouritesView  # noqa: F401 (registruje klasu za .kv)
from app.screens.search_view import SearchView  # noqa: F401 (registruje klasu za .kv)
from app.screens.settings_view import SettingsView  # noqa: F401 (registruje klasu za .kv)
from app.services.factory import (
    STORAGE_MEMORY,
    STORAGE_ON,
    STORAGE_UNAVAILABLE,
    create_services,
)
from app.services.settings_service import (
    DEFINITIONS,
    LANGUAGE,
    REFRESH,
    THEME,
    TIME_FORMAT,
    TIME_ZONE,
    refresh_policy,
)
from app.strings import DEFAULT_LANGUAGE, t as translate
from app.theme import COLORS, DEFAULT_THEME, PALETTES, THEME_STYLES
from app.utils.android_insets import get_system_insets
from app.utils.clockfmt import ClockFormat
from app.utils.devicezone import detect_device_zone_name
from app.version import __version__

_LOGGER = logging.getLogger(__name__)

KV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "main.kv")

INSET_RETRY_SECONDS = 0.5
INSET_MAX_TRIES = 20
INSET_RECHECKS = 3
# Koliko dugo se pamti prepoznata zona uredjaja (putnik moze da je promeni dok je aplikacija otvorena)
DEVICE_ZONE_CACHE_SECONDS = 300


class TvProgramGlobalApp(MDApp):
    title = "TV Program Global"
    colors = DictProperty(COLORS)
    language = StringProperty(DEFAULT_LANGUAGE)
    runtime_info = StringProperty("")
    # Prostor za sistemske trake, u pikselima (koristi se u main.kv)
    inset_top = NumericProperty(0)
    inset_bottom = NumericProperty(0)
    # Servis pretrage (None ako katalog stanica ne moze da se otvori)
    search_service = ObjectProperty(None, allownone=True)
    # Servis rasporeda (None ako katalog stanica ne moze da se otvori)
    schedule_service = ObjectProperty(None, allownone=True)
    # Servis omiljenih stanica (None ako trajno cuvanje nije dostupno)
    favourites_service = ObjectProperty(None, allownone=True)
    # Raste pri svakoj promeni omiljenih; ekrani se prema tome osvezavaju
    favourites_version = NumericProperty(0)
    # Poslednja stanica koju je korisnik izabrao u pretrazi
    selected_channel = ObjectProperty(None, allownone=True)
    # Servis podesavanja (jezik, tema, vreme, osvezavanje); radi i bez trajnog cuvanja
    settings_service = ObjectProperty(None, allownone=True)
    # Naziv teme ("dark" ili "light")
    theme_name = StringProperty(DEFAULT_THEME)
    # Raste pri svakoj promeni podesavanja; ekrani se prema tome ponovo crtaju
    ui_version = NumericProperty(0)
    # Stanje trajnog cuvanja (vidi app.services.factory) i opis greske, ako postoji
    storage_state = StringProperty(STORAGE_UNAVAILABLE)
    storage_detail = StringProperty("")

    _inset_tries = 0
    _inset_rechecks = 0
    _device_zone = None  # (ZoneInfo ili None, naziv ili None, vreme provere)

    def t(self, key, _language=None):
        """Tekst interfejsa za trenutni jezik (poziva se iz .kv fajla).

        Drugi argument je samo zato da .kv izraz `app.t("kljuc", app.language)` zavisi od
        `app.language` i da se tekst promeni cim se jezik promeni.
        """
        return translate(key, _language or self.language)

    # ---- podesavanja ---------------------------------------------------------

    def setting(self, key):
        """Trenutna vrednost podesavanja (podrazumevana ako servis ne postoji)."""
        if self.settings_service is not None:
            return self.settings_service.get(key)
        return next(item.default for item in DEFINITIONS if item.key == key)

    def set_setting(self, key, value):
        """Menja podesavanje i odmah osvezava prikaz. Vraca True ako je i trajno sacuvano."""
        service = self.settings_service
        if service is None:
            return False
        try:
            saved = service.set(key, value)
        except ValueError as error:
            _LOGGER.warning("Podesavanje odbijeno: %s", error)
            return False
        self._apply_setting(key)
        self.ui_version += 1
        return saved

    def _apply_setting(self, key):
        value = self.setting(key)
        if key == LANGUAGE:
            self.language = value
            self._refresh_runtime_info()
        elif key == THEME:
            self.theme_name = value
            self.theme_cls.theme_style = THEME_STYLES[value]
            self.colors = dict(PALETTES[value])
        elif key == TIME_ZONE:
            self._device_zone = None  # sledeci prikaz ponovo prepoznaje zonu
        elif key == REFRESH:
            self._apply_refresh_policy()

    def _apply_all_settings(self):
        for key in (LANGUAGE, THEME, TIME_FORMAT, TIME_ZONE, REFRESH):
            self._apply_setting(key)

    def on_schedule_service(self, _instance, _value):
        self._apply_refresh_policy()  # i kad se servis zameni (npr. u testovima)

    def _apply_refresh_policy(self):
        setter = getattr(self.schedule_service, "set_refresh_policy", None)
        if setter is None:
            return
        min_seconds, manual_only = refresh_policy(self.setting(REFRESH))
        setter(min_seconds, manual_only)

    def device_zone(self):
        """(ZoneInfo, naziv) zone uredjaja ili (None, None) ako se ne moze utvrditi."""
        cached = self._device_zone
        if cached is None or time.monotonic() - cached[2] > DEVICE_ZONE_CACHE_SECONDS:
            name = detect_device_zone_name()
            zone = ZoneInfo(name) if name else None
            cached = self._device_zone = (zone, name, time.monotonic())
        return cached[0], cached[1]

    def clock_format(self):
        """Prikaz vremena prema podesavanjima (12/24 h, zona stanice ili uredjaja)."""
        zone = None
        if self.setting(TIME_ZONE) == "device":
            zone, _name = self.device_zone()  # None: ostaje zona stanice
        return ClockFormat(self.setting(TIME_FORMAT) == "12h", zone)

    def _user_data_directory(self):
        """Folder za trajne podatke. Promenljiva TVPG_USER_DATA_DIR je samo za testove i razvoj."""
        return os.environ.get("TVPG_USER_DATA_DIR") or self.user_data_dir

    def favourites_changed(self):
        """Javlja ekranima da se spisak omiljenih promenio."""
        self.favourites_version += 1

    def open_channel_schedule(self, channel, origin="favourites"):
        """Otvara raspored stanice na kartici Pretraga (npr. iz Omiljenih)."""
        self.root.ids.nav.switch_tab("search")
        self.root.ids.search_view.open_schedule(channel, origin=origin)

    def show_favourites_tab(self):
        self.root.ids.nav.switch_tab("favourites")

    def build(self):
        self.theme_cls.primary_palette = "Amber"
        services = create_services(self._user_data_directory())
        self.search_service = services.search
        self.schedule_service = services.schedule
        self.favourites_service = services.favourites
        self.settings_service = services.settings
        self.storage_state = services.storage_state
        self.storage_detail = services.storage_detail
        self._apply_all_settings()  # jezik, tema i osvezavanje vaze od prvog crtanja
        self._refresh_runtime_info()
        Window.bind(on_resize=self._on_window_resize)
        Builder.unload_file(KV_PATH)  # ne dozvoljava dvostruko ucitavanje pravila
        return Builder.load_file(KV_PATH)

    def on_pause(self):
        """Android: bez ovoga se aplikacija zatvara cim korisnik predje na drugu aplikaciju."""
        return True

    def on_resume(self):
        self._device_zone = None  # putnik je mozda promenio zonu dok je aplikacija bila u pozadini
        self.ui_version += 1  # ponovo crta prikaz (Sada/Sledece, vreme) sa tacnim satom

    def on_start(self):
        self._restart_inset_updates(0)

    def _on_window_resize(self, *_args):
        self._restart_inset_updates(0.2)

    def _restart_inset_updates(self, delay):
        self._inset_tries = 0
        self._inset_rechecks = 0
        Clock.schedule_once(self._update_insets, delay)

    def _update_insets(self, _dt):
        insets = get_system_insets()
        if insets is None:
            self._inset_tries += 1
            if self._inset_tries < INSET_MAX_TRIES:
                Clock.schedule_once(self._update_insets, INSET_RETRY_SECONDS)
            return
        self.inset_top, self.inset_bottom = insets
        self._refresh_runtime_info()
        # Nekoliko dodatnih provera, jer Android ponekad javi prave vrednosti kasnije
        if self._inset_rechecks < INSET_RECHECKS:
            self._inset_rechecks += 1
            Clock.schedule_once(self._update_insets, 1.0)

    def _catalog_info(self):
        if self.search_service is None:
            return self.t("about_unavailable")
        try:
            summary = self.search_service.catalog_summary()
        except Exception as error:  # samo informacija za prikaz
            Logger.warning("TVPG: opis kataloga nije dostupan: %s", error)
            return self.t("about_unavailable")
        return self.t("about_catalog_value").format(
            count=summary["channels"], commit=summary["source_commit"][:7])

    def _providers_info(self):
        if self.schedule_service is None:
            return self.t("about_providers_unavailable")
        summary = self.schedule_service.provider_summary()
        if not summary:
            return self.t("about_providers_none")
        return ", ".join(
            self.t("about_provider_license").format(id=source_id, status=status)
            for source_id, status in summary)

    def _storage_info(self):
        if self.storage_state == STORAGE_ON:
            return self.t("about_storage_on")
        if self.storage_state == STORAGE_MEMORY:
            return self.t("about_storage_memory")
        if self.storage_detail:
            return self.t("about_storage_unavailable_detail").format(detail=self.storage_detail)
        return self.t("about_storage_unavailable")

    def _refresh_runtime_info(self):
        self.runtime_info = self.t("about_runtime").format(
            version=__version__,
            python=sys.version.split()[0],
            kivy=kivy.__version__,
            kivymd=kivymd.__version__,
            platform=platform,
            inset_top=self.inset_top,
            inset_bottom=self.inset_bottom,
            catalog=self._catalog_info(),
            providers=self._providers_info(),
            storage=self._storage_info(),
            flavor=FLAVOR,
        )
