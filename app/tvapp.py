"""Glavna aplikaciona klasa (KivyMD)."""

import os
import sys

import kivy
import kivymd
from kivy.lang import Builder
from kivy.properties import DictProperty, StringProperty
from kivy.utils import platform
from kivymd.app import MDApp

from app.strings import DEFAULT_LANGUAGE, t as translate
from app.theme import COLORS
from app.version import __version__

KV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "main.kv")


class TvProgramGlobalApp(MDApp):
    title = "TV Program Global"
    colors = DictProperty(COLORS)
    language = StringProperty(DEFAULT_LANGUAGE)
    runtime_info = StringProperty("")

    def t(self, key):
        """Tekst interfejsa za trenutni jezik (poziva se iz .kv fajla)."""
        return translate(key, self.language)

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Amber"
        self.runtime_info = (
            "Verzija aplikacije: %s\n"
            "Python: %s\n"
            "Kivy: %s\n"
            "KivyMD: %s\n"
            "Platforma: %s"
        ) % (
            __version__,
            sys.version.split()[0],
            kivy.__version__,
            kivymd.__version__,
            platform,
        )
        return Builder.load_file(KV_PATH)
