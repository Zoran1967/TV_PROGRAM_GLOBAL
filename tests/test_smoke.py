"""Osnovni testovi Faze 2: tekstovi, verzija i izgradnja UI stabla."""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.strings import STRINGS, t  # noqa: E402

KV_PATH = os.path.join(ROOT, "app", "ui", "main.kv")


def test_missing_key_is_visible():
    assert t("ne_postoji") == "[ne_postoji]"


def test_unknown_language_falls_back_to_serbian():
    assert t("app_title", "xx") == STRINGS["sr"]["app_title"]


def test_every_key_used_in_kv_exists():
    with open(KV_PATH, encoding="utf-8") as handle:
        kv_text = handle.read()
    used = set(re.findall(r'app\.t\("([a-z_]+)"\)', kv_text))
    assert used, "kv fajl ne koristi nijedan tekst"
    missing = used - set(STRINGS["sr"])
    assert not missing, "nedostaju kljucevi: %s" % sorted(missing)


def test_version_format():
    from app.version import __version__

    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_ui_tree_builds():
    pytest.importorskip("kivymd")
    if not os.environ.get("DISPLAY") and not os.environ.get("KIVY_GL_BACKEND"):
        pytest.skip("nema ekrana za Kivy prozor")
    os.environ.setdefault("KIVY_NO_ARGS", "1")
    from kivy.clock import Clock
    from kivy.core.window import Window
    from app.tvapp import TvProgramGlobalApp

    app = TvProgramGlobalApp()
    root = app.build()
    Window.add_widget(root)
    try:
        for _ in range(5):
            Clock.tick()
        nav = next(
            widget
            for widget in root.walk()
            if widget.__class__.__name__ == "MDBottomNavigation"
        )
        names = {screen.name for screen in nav.ids.tab_manager.screens}
    finally:
        Window.remove_widget(root)
    assert names == {"search", "favourites", "settings"}
    assert "Python:" in app.runtime_info
