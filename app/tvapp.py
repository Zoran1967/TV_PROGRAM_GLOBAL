"""Glavna aplikaciona klasa (KivyMD)."""

import os
import sys

import kivy
import kivymd
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import DictProperty, NumericProperty, StringProperty
from kivy.utils import platform
from kivymd.app import MDApp

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

    _inset_tries = 0
    _inset_rechecks = 0

    def t(self, key):
        """Tekst interfejsa za trenutni jezik (poziva se iz .kv fajla)."""
        return translate(key, self.language)

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Amber"
        self._refresh_runtime_info()
        Window.bind(on_resize=self._on_window_resize)
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

    def _refresh_runtime_info(self):
        self.runtime_info = (
            "Verzija aplikacije: %s\n"
            "Python: %s\n"
            "Kivy: %s\n"
            "KivyMD: %s\n"
            "Platforma: %s\n"
            "Sistemske trake (gore/dole): %d / %d px"
        ) % (
            __version__,
            sys.version.split()[0],
            kivy.__version__,
            kivymd.__version__,
            platform,
            self.inset_top,
            self.inset_bottom,
        )
