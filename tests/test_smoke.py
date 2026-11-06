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


def test_kv_uses_system_insets():
    with open(KV_PATH, encoding="utf-8") as handle:
        kv_text = handle.read()
    assert "app.inset_top" in kv_text
    assert "app.inset_bottom" in kv_text


def test_insets_outside_android_are_zero():
    from app.utils import android_insets

    assert android_insets.get_system_insets() == (0, 0)


def _fake_jnius(sdk, insets_obj):
    import types

    class Namespace:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    view = Namespace(getRootWindowInsets=lambda: insets_obj)
    window = Namespace(getDecorView=lambda: view)
    activity = Namespace(getWindow=lambda: window)
    classes = {
        "org.kivy.android.PythonActivity": Namespace(mActivity=activity),
        "android.os.Build$VERSION": Namespace(SDK_INT=sdk),
        "android.view.WindowInsets$Type": Namespace(
            systemBars=lambda: 1, displayCutout=lambda: 128
        ),
    }
    module = types.ModuleType("jnius")
    module.autoclass = lambda name: classes[name]
    return module


class _Insets30:
    def getInsets(self, mask):
        assert mask == 129
        return type("Bars", (), {"top": 80, "bottom": 130})()


class _InsetsOld:
    def getSystemWindowInsetTop(self):
        return 60

    def getSystemWindowInsetBottom(self):
        return 90


@pytest.mark.parametrize(
    "sdk, insets_obj, expected",
    [
        (36, _Insets30(), (80, 130)),
        (28, _InsetsOld(), (60, 90)),
        (36, None, None),
    ],
)
def test_android_insets_logic(monkeypatch, sdk, insets_obj, expected):
    from app.utils import android_insets

    monkeypatch.setattr(android_insets, "is_android", lambda: True)
    monkeypatch.setitem(sys.modules, "jnius", _fake_jnius(sdk, insets_obj))
    assert android_insets.get_system_insets() == expected


def test_android_insets_error_returns_none(monkeypatch):
    import types
    from app.utils import android_insets

    broken = types.ModuleType("jnius")

    def fail(_name):
        raise RuntimeError("JNI greska")

    broken.autoclass = fail
    monkeypatch.setattr(android_insets, "is_android", lambda: True)
    monkeypatch.setitem(sys.modules, "jnius", broken)
    assert android_insets.get_system_insets() is None


def test_search_screen_flow():
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
        view = next(w for w in root.walk() if w.__class__.__name__ == "SearchView")
        assert app.search_service is not None
        assert "Katalog stanica:" in app.runtime_info
        assert view.status_text == app.t("search_examples")

        view.run_search("RTS 1")
        items = list(view.ids.results.children)
        assert len(items) >= 3
        assert any(
            item.text == "RTS 1" and "Serbia (RS)" in item.secondary_text
            for item in items
        )
        assert view.status_text.startswith("Pronađeno stanica:")

        view.run_search("xqzvjk")
        assert not view.ids.results.children
        assert view.status_text == app.t("search_not_found")

        view.run_search("a")
        assert view.status_text == app.t("search_too_short")

        view.run_search("BBC1")
        item = view.ids.results.children[0]
        assert "pronađeno kao: BBC1" in item.secondary_text
        item.dispatch("on_release")
        assert app.selected_channel.catalog_id == "BBCOne.uk"
        assert view.selected_text.startswith("Izabrano: BBC One (United Kingdom)")

        # debounce: tekst se unosi u polje, a pretraga se pokrece posle kratke pauze
        view.ids.query.text = "HRT1"
        # pretraga je zakazana, ali jos nije pokrenuta
        assert view._pending is not None
        import time as _time
        _time.sleep(0.4)
        for _ in range(3):
            Clock.tick()
        assert [i.text for i in view.ids.results.children] == ["HRT 1"]
    finally:
        Window.remove_widget(root)
