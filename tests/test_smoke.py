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


def _build_app_view():
    from kivy.clock import Clock
    from kivy.core.window import Window
    from app.tvapp import TvProgramGlobalApp

    app = TvProgramGlobalApp()
    root = app.build()
    Window.add_widget(root)
    for _ in range(5):
        Clock.tick()
    view = next(w for w in root.walk() if w.__class__.__name__ == "SearchView")
    return app, root, view


def _needs_display():
    pytest.importorskip("kivymd")
    if not os.environ.get("DISPLAY") and not os.environ.get("KIVY_GL_BACKEND"):
        pytest.skip("nema ekrana za Kivy prozor")
    os.environ.setdefault("KIVY_NO_ARGS", "1")


def _wait_until(condition, timeout=3.0):
    import time as _time
    from kivy.clock import Clock

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        Clock.tick()
        if condition():
            return True
        _time.sleep(0.01)
    return False


def test_search_screen_flow():
    _needs_display()
    from kivy.core.window import Window

    app, root, view = _build_app_view()
    try:
        assert app.search_service is not None and app.schedule_service is not None
        assert "Katalog stanica:" in app.runtime_info
        assert "tvprofil" in app.runtime_info and "Vrsta izgradnje:" in app.runtime_info
        assert view.status_text == app.t("search_examples")

        view.run_search("RTS 1")
        items = list(view.ids.results.children)
        assert len(items) >= 3
        assert any(
            item.text == "RTS 1" and "Serbia (RS)" in item.secondary_text for item in items
        )
        assert view.status_text.startswith("Pronađeno stanica:")

        view.run_search("xqzvjk")
        assert not view.ids.results.children
        assert view.status_text == app.t("search_not_found")

        view.run_search("a")
        assert view.status_text == app.t("search_too_short")

        # stanica bez izvora rasporeda (BBC One nema TvProfil kanal)
        view.run_search("BBC1")
        item = view.ids.results.children[0]
        assert "pronađeno kao: BBC1" in item.secondary_text
        item.dispatch("on_release")
        assert app.selected_channel.catalog_id == "BBCOne.uk"
        assert view.in_schedule
        assert "Raspored: BBC One (United Kingdom)" in view.schedule_text
        assert "nema povezanog izvora rasporeda" in view.schedule_text
        assert not view.ids.results.children

        # povratak na rezultate
        view.show_results()
        assert not view.in_schedule and view.schedule_text == ""
        assert len(view.ids.results.children) == 1
        assert view.status_text.startswith("Pronađeno stanica:")

        # debounce
        view.ids.query.text = "HRT1"
        assert view._pending is not None
        assert _wait_until(lambda: [i.text for i in view.ids.results.children] == ["HRT 1"])
    finally:
        Window.remove_widget(root)


class StubSchedule:
    """Zamena za ScheduleService: nikad ne koristi mrezu."""

    def __init__(self, outcome_factory, delay=0.0):
        self.outcome_factory = outcome_factory
        self.delay = delay
        self.calls = []

    def sources_for(self, channel):
        return ["izvor"]

    def provider_summary(self):
        return [("tvprofil", "pending")]

    def get_schedule(self, channel, sources=None, force=False):
        import time as _time

        self.calls.append(channel.catalog_id)
        if self.delay:
            _time.sleep(self.delay)
        return self.outcome_factory(channel)


def _outcome(channel, status="ok", **kwargs):
    import datetime
    from zoneinfo import ZoneInfo
    from app.services.schedule_service import ScheduleEntry, ScheduleOutcome, ScheduleStatus

    zone = ZoneInfo("Europe/Belgrade")

    def at(hour, minute):
        return datetime.datetime(2026, 11, 6, hour, minute, tzinfo=zone)

    entries = ()
    if status == "ok":
        entries = (
            ScheduleEntry(at(19, 30), at(20, 0), "Dnevnik", "Vesti dana", "Informativni"),
            ScheduleEntry(at(20, 0), None, "Film", "Dugacak opis " * 20, None),
        )
    defaults = dict(
        status=ScheduleStatus.OK if status == "ok" else ScheduleStatus[status.upper()],
        channel=channel, source_name="TvProfil", license_status="pending",
        timezone="Europe/Belgrade", zone_label="CET",
        local_date=datetime.date(2026, 11, 6), entries=entries, fetched_at=1793990000,
    )
    defaults.update(kwargs)
    return ScheduleOutcome(**defaults)


def _select_rts1_serbia(view):
    view.run_search("RTS 1")
    item = next(i for i in view.ids.results.children
                if i.text == "RTS 1" and "Serbia" in i.secondary_text)
    item.dispatch("on_release")


def test_schedule_is_shown_with_zone_source_and_license_note():
    _needs_display()
    from kivy.core.window import Window

    app, root, view = _build_app_view()
    try:
        app.schedule_service = StubSchedule(lambda channel: _outcome(channel))
        _select_rts1_serbia(view)
        assert view.in_schedule and "Učitavam raspored" in view.schedule_text
        assert _wait_until(lambda: "Učitavam" not in view.schedule_text)
        text = view.schedule_text
        assert "Raspored: RTS 1 (Serbia)" in text
        assert "Datum: 06.11.2026. · Zona: Europe/Belgrade (CET)" in text
        assert "Izvor: TvProfil" in text
        assert "Probna verzija: licenca izvora nije potvrđena." in text
        rows = [(i.text, i.secondary_text) for i in reversed(view.ids.results.children)]
        assert rows[0] == ("19:30-20:00  Dnevnik", "Informativni")
        assert rows[1][0] == "20:00  Film" and rows[1][1].endswith("...") and len(rows[1][1]) == 90
    finally:
        Window.remove_widget(root)


@pytest.mark.parametrize("status, extra, expected", [
    ("network_error", {}, "nema veze"),
    ("http_error", {"http_status": 404}, "greška 404"),
    ("http_error", {"http_status": 500}, "grešku (500)"),
    ("rate_limited", {}, "traži pauzu"),
    ("empty", {}, "nema emisije"),
    ("parse_error", {}, "nisu ispravni"),
    ("zone_unavailable", {}, "zona stanice nije poznata"),
    ("error", {}, "neočekivane greške"),
    ("source_unavailable", {}, "nije dostupan u ovoj verziji"),
    ("no_data_for_date", {}, "nema program za današnji datum (06.11.2026.)"),
])
def test_schedule_errors_are_explained_and_list_is_empty(status, extra, expected):
    _needs_display()
    from kivy.core.window import Window

    app, root, view = _build_app_view()
    try:
        app.schedule_service = StubSchedule(lambda channel: _outcome(channel, status, **extra))
        _select_rts1_serbia(view)
        assert _wait_until(lambda: "Učitavam" not in view.schedule_text)
        assert expected in view.schedule_text
        assert not view.ids.results.children
    finally:
        Window.remove_widget(root)


def test_stale_schedule_says_why_refresh_failed():
    _needs_display()
    from kivy.core.window import Window
    from app.services.schedule_service import ScheduleStatus

    app, root, view = _build_app_view()
    try:
        app.schedule_service = StubSchedule(lambda channel: _outcome(
            channel, stale=True, error_status=ScheduleStatus.NETWORK_ERROR))
        _select_rts1_serbia(view)
        assert _wait_until(lambda: "Učitavam" not in view.schedule_text)
        assert "Prikazani su stariji podaci. Osvežavanje nije uspelo: Raspored nije preuzet" in view.schedule_text
        assert len(view.ids.results.children) == 2
    finally:
        Window.remove_widget(root)


def test_crash_in_service_is_shown_as_error_not_raised():
    _needs_display()
    from kivy.core.window import Window

    def boom(channel):
        raise RuntimeError("neocekivano")

    app, root, view = _build_app_view()
    try:
        app.schedule_service = StubSchedule(boom)
        _select_rts1_serbia(view)
        assert _wait_until(lambda: "Učitavam" not in view.schedule_text)
        assert "neočekivane greške" in view.schedule_text
    finally:
        Window.remove_widget(root)


def test_late_answer_for_previous_channel_is_ignored():
    _needs_display()
    from kivy.core.window import Window

    app, root, view = _build_app_view()
    try:
        app.schedule_service = StubSchedule(lambda channel: _outcome(channel), delay=0.4)
        _select_rts1_serbia(view)            # spor odgovor
        view.show_results()                   # korisnik se vraca nazad pre odgovora
        assert _wait_until(lambda: len(app.schedule_service.calls) == 1)
        import time as _time
        _time.sleep(0.6)
        for _ in range(5):
            from kivy.clock import Clock
            Clock.tick()
        assert not view.in_schedule and view.schedule_text == ""
        assert all(not i.text.startswith("19:30") for i in view.ids.results.children)
    finally:
        Window.remove_widget(root)
