"""Glavna aplikaciona klasa (KivyMD)."""

import os
import sys

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
from app.services.factory import create_services
from app.strings import DEFAULT_LANGUAGE, t as translate
from app.theme import COLORS
from app.utils.android_insets import get_system_insets
from app.version import __version__

KV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "main.kv")

INSET_RETRY_SECONDS = 0.5
INSET_MAX_TRIES = 20
INSET_RECHECKS = 3


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
    # Opis stanja trajnog cuvanja (za Podesavanja)
    storage_info = StringProperty("")

    _inset_tries = 0
    _inset_rechecks = 0

    def t(self, key):
        """Tekst interfejsa za trenutni jezik (poziva se iz .kv fajla)."""
        return translate(key, self.language)

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
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Amber"
        services = create_services(self._user_data_directory())
        self.search_service = services.search
        self.schedule_service = services.schedule
        self.favourites_service = services.favourites
        self.storage_info = services.storage_info
        self._refresh_runtime_info()
        Window.bind(on_resize=self._on_window_resize)
        Builder.unload_file(KV_PATH)  # ne dozvoljava dvostruko ucitavanje pravila
        return Builder.load_file(KV_PATH)

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
            return "nedostupan"
        try:
            summary = self.search_service.catalog_summary()
        except Exception as error:  # samo informacija za prikaz
            Logger.warning("TVPG: opis kataloga nije dostupan: %s", error)
            return "nedostupan"
        return "%d stanica (iptv-org, CC0, %s)" % (
            summary["channels"],
            summary["source_commit"][:7],
        )

    def _providers_info(self):
        if self.schedule_service is None:
            return "nedostupni"
        summary = self.schedule_service.provider_summary()
        if not summary:
            return "nijedan (licenca nije potvrđena)"
        return ", ".join("%s (licenca: %s)" % item for item in summary)

    def _refresh_runtime_info(self):
        self.runtime_info = (
            "Verzija aplikacije: %s\n"
            "Python: %s\n"
            "Kivy: %s\n"
            "KivyMD: %s\n"
            "Platforma: %s\n"
            "Sistemske trake (gore/dole): %d / %d px\n"
            "Katalog stanica: %s\n"
            "Izvori rasporeda: %s\n"
            "Trajno čuvanje (omiljene, keš): %s\n"
            "Vrsta izgradnje: %s"
        ) % (
            __version__,
            sys.version.split()[0],
            kivy.__version__,
            kivymd.__version__,
            platform,
            self.inset_top,
            self.inset_bottom,
            self._catalog_info(),
            self._providers_info(),
            self.storage_info,
            FLAVOR,
        )
