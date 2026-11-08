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
    used = set(re.findall(r'app\.t\("([a-z_0-9]+)", app\.language\)', kv_text))
    assert used, "kv fajl ne koristi nijedan tekst"
    for language, table in STRINGS.items():
        missing = used - set(table)
        assert not missing, "nedostaju kljucevi (%s): %s" % (language, sorted(missing))
    # Svaki tekst mora da zavisi od app.language, inace se ne menja sa jezikom
    assert not re.findall(r'app\.t\("[a-z_0-9]+"\)', kv_text)


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
            item.text == "RTS 1" and "Srbija (RS)" in item.secondary_text for item in items
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
        assert "Raspored: BBC One (Ujedinjeno Kraljevstvo)" in view.schedule_text
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
        self.forces = []
        self.view = None  # sta vraca refresh_view (None = nema nista u kesu)

    def sources_for(self, channel):
        return ["izvor"]

    def provider_summary(self):
        return [("tvprofil", "pending")]

    def refresh_view(self, channel, sources):
        return self.view

    def get_schedule(self, channel, sources=None, force=False):
        import time as _time

        self.calls.append(channel.catalog_id)
        self.forces.append(force)
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
                if i.text == "RTS 1" and "Srbija" in i.secondary_text)
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
        assert "Raspored: RTS 1 (Srbija)" in text
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



# ---- Faza 5: formatiranje, Sada/Sledece na ekranu, osvezavanje prikaza ---------------

class _T:
    """Minimalna zamena aplikacije za funkcije formatiranja."""

    @staticmethod
    def t(key):
        from app.strings import t as translate
        return translate(key)


@pytest.mark.parametrize("seconds, expected", [
    (-5, "manje od minut"), (0, "manje od minut"), (59, "manje od minut"), (60, "1 min"),
    (3599, "59 min"), (3600, "1 h"), (3660, "1 h 1 min"), (7325, "2 h 2 min"),
])
def test_format_age(seconds, expected):
    pytest.importorskip("kivymd")
    from app.screens.search_view import format_age

    assert format_age(_T, seconds) == expected


def test_time_range_marks_yesterday_and_tomorrow():
    pytest.importorskip("kivymd")
    import datetime
    from zoneinfo import ZoneInfo
    from app.screens.search_view import time_range
    from app.services.schedule_service import ScheduleEntry

    zone = ZoneInfo("Europe/Belgrade")

    def at(day, hour, minute):
        return datetime.datetime(2026, 11, day, hour, minute, tzinfo=zone)

    today = datetime.date(2026, 11, 6)
    assert time_range(_T, ScheduleEntry(at(5, 23, 0), at(6, 0, 30), "A"), today) == "juče 23:00-00:30"
    assert time_range(_T, ScheduleEntry(at(6, 23, 30), at(7, 1, 30), "B"), today) == "23:30-01:30 (sutra)"
    assert time_range(_T, ScheduleEntry(at(6, 10, 0), None, "C"), today) == "10:00"
    assert time_range(_T, ScheduleEntry(at(6, 10, 0), at(6, 11, 0), "D"), today) == "10:00-11:00"


def test_list_item_properties_used_for_styling_exist():
    _needs_display()
    from kivy.uix.scrollview import ScrollView
    from kivymd.uix.list import OneLineListItem, TwoLineListItem

    for name in ("bg_color", "theme_text_color", "secondary_theme_text_color"):
        assert name in TwoLineListItem().properties(), name
    for name in ("theme_text_color", "bg_color", "text_color"):
        assert name in OneLineListItem().properties(), name  # ekran Podesavanja
    assert hasattr(ScrollView, "scroll_to")


def _real_service(clock, provider):
    from app.models.schedule import ChannelSource
    from app.providers.registry import ProviderRegistry
    from app.services.schedule_service import ScheduleService

    class Catalog:
        def sources_for(self, channel_id):
            return [ChannelSource("tvprofil", "rts1.sr", "Europe/Belgrade", 7, 0)]

    return ScheduleService(Catalog(), ProviderRegistry({"tvprofil": provider}), clock=clock)


def _fake_provider(programmes, refresh=3600):
    from app.providers.base import ProviderInfo, ScheduleProvider

    class Fake(ScheduleProvider):
        calls = 0

        def fetch_programmes(self, source):
            type(self).calls += 1
            return list(programmes)

    fake = Fake()
    fake.info = ProviderInfo("tvprofil", "TvProfil", "pending", "x", "y", refresh)
    return fake


def _belgrade(*args):
    import datetime
    from zoneinfo import ZoneInfo

    return int(datetime.datetime(*args, tzinfo=ZoneInfo("Europe/Belgrade")).timestamp())


def _day_programmes():
    from app.models.schedule import Programme

    return [
        Programme("Juce uvece", _belgrade(2026, 11, 5, 23, 0), _belgrade(2026, 11, 6, 0, 30)),
        Programme("Jutro", _belgrade(2026, 11, 6, 6, 0), _belgrade(2026, 11, 6, 7, 0), "Opis jutra", "Informativni"),
        Programme("Dnevnik", _belgrade(2026, 11, 6, 19, 30), _belgrade(2026, 11, 6, 20, 0)),
        Programme("Nocni film", _belgrade(2026, 11, 6, 23, 30), _belgrade(2026, 11, 7, 1, 30)),
    ]


def test_now_next_gaps_and_freshness_on_screen_and_time_moves_without_network():
    _needs_display()
    from kivy.core.window import Window

    class Clock:
        now = _belgrade(2026, 11, 6, 19, 45)

        def __call__(self):
            return self.now

    clock = Clock()
    provider = _fake_provider(_day_programmes())
    app, root, view = _build_app_view()
    try:
        app.schedule_service = _real_service(clock, provider)
        _select_rts1_serbia(view)
        assert _wait_until(lambda: "Učitavam" not in view.schedule_text)
        text = view.schedule_text
        assert "Vreme u stanici: 19:45 (CET)" in text
        assert "Sada: Dnevnik (do 20:00) · još 15 min" in text
        assert "Sledeće: Nocni film u 23:30" in text
        assert "Ažurno · osveženo 19:45 (pre manje od minut)" in text
        rows = [i.text for i in reversed(view.ids.results.children)]
        assert "juče 23:00-00:30  Juce uvece" in rows
        assert "SADA  19:30-20:00  Dnevnik" in rows
        assert "SLEDEĆE  23:30-01:30 (sutra)  Nocni film" in rows
        assert rows.count("Nema podataka od 00:30 do 06:00") == 1
        assert sum(1 for r in rows if r.startswith("Nema podataka od")) == 3
        current_item = next(i for i in view.ids.results.children if i.text.startswith("SADA"))
        assert current_item.secondary_text == "još 15 min"
        assert list(current_item.bg_color)[3] > 0
        past_item = next(i for i in view.ids.results.children if i.text.endswith("Jutro"))
        assert past_item.theme_text_color == "Hint"

        # protice vreme: Sada nestaje, Sledece ostaje; bez novog preuzimanja
        clock.now = _belgrade(2026, 11, 6, 20, 5)
        view._tick(0)
        assert "Sada: nema emisije u rasporedu za ovaj trenutak." in view.schedule_text
        assert "Sledeće: Nocni film u 23:30" in view.schedule_text
        rows = [i.text for i in reversed(view.ids.results.children)]
        assert not any(r.startswith("SADA") for r in rows)
        assert any(r.startswith("SLEDEĆE") for r in rows)
        assert type(provider).calls == 1

        # ista minuta: lista se ne crta ponovo (ne skace skrol), zaglavlje se osvezava
        before = list(view.ids.results.children)
        clock.now += 20
        view._tick(0)
        assert list(view.ids.results.children) == before
        assert "(pre 20 min)" in view.schedule_text or "(pre 21 min)" in view.schedule_text
    finally:
        Window.remove_widget(root)


def test_midnight_switches_the_day_on_screen_without_network():
    _needs_display()
    from kivy.core.window import Window
    from app.models.schedule import Programme

    class Clock:
        now = _belgrade(2026, 11, 6, 23, 58)

        def __call__(self):
            return self.now

    programmes = _day_programmes() + [
        Programme("Sutradan", _belgrade(2026, 11, 7, 8, 0), _belgrade(2026, 11, 7, 9, 0))]
    clock = Clock()
    provider = _fake_provider(programmes)
    app, root, view = _build_app_view()
    try:
        app.schedule_service = _real_service(clock, provider)
        _select_rts1_serbia(view)
        assert _wait_until(lambda: "Učitavam" not in view.schedule_text)
        assert "Datum: 06.11.2026." in view.schedule_text
        clock.now = _belgrade(2026, 11, 7, 0, 1)
        view._tick(0)
        assert "Datum: 07.11.2026." in view.schedule_text
        assert "Sada: Nocni film (do 01:30) · još 1 h 29 min" in view.schedule_text
        rows = [i.text for i in reversed(view.ids.results.children)]
        assert rows[0] == "SADA  juče 23:30-01:30  Nocni film" or rows[0].startswith("SADA")
        assert any(r.endswith("Sutradan") for r in rows)
        assert type(provider).calls == 1
    finally:
        Window.remove_widget(root)


def test_refresh_button_asks_for_new_data_and_tick_reload_is_throttled():
    _needs_display()
    from kivy.core.window import Window

    app, root, view = _build_app_view()
    try:
        stub = StubSchedule(lambda channel: _outcome(channel, "network_error"))
        app.schedule_service = stub
        _select_rts1_serbia(view)
        assert _wait_until(lambda: "Učitavam" not in view.schedule_text)
        assert stub.forces == [False]

        view._tick(0)                       # greska i nema kesa, ali je tek pokusano
        assert stub.calls == ["RTS1.rs"]

        view._last_reload -= 400            # proslo je vise od 5 minuta
        view._tick(0)
        assert _wait_until(lambda: len(stub.calls) == 2)

        view.refresh_schedule()             # dugme Osvezi
        assert _wait_until(lambda: len(stub.calls) == 3)
        assert stub.forces == [False, False, True]
    finally:
        Window.remove_widget(root)


def test_leaving_the_schedule_stops_the_clock_tick():
    _needs_display()
    from kivy.core.window import Window

    app, root, view = _build_app_view()
    try:
        app.schedule_service = StubSchedule(lambda channel: _outcome(channel))
        _select_rts1_serbia(view)
        assert _wait_until(lambda: view._tick_event is not None)
        view.show_results()
        assert view._tick_event is None and view._channel is None
        view.run_search("RTS 1")
        assert view._tick_event is None
    finally:
        Window.remove_widget(root)


def test_tapping_a_programme_opens_details_with_film_and_series_notes():
    _needs_display()
    import datetime
    from zoneinfo import ZoneInfo
    from kivy.clock import Clock
    from kivy.core.window import Window
    from app.models.schedule import Programme
    from app.services.schedule_service import ScheduleEntry

    zone = ZoneInfo("Europe/Belgrade")

    def at(hour, minute):
        return datetime.datetime(2026, 11, 6, hour, minute, tzinfo=zone)

    film = Programme("Dugi film", 0, 0, "Opis filma.", "Film", year=2019,
                     directors=("Reditelj Prvi",), actors=("Glumac Jedan",))
    series = Programme("Serijal", 0, 0, "Opis epizode.", "Serija", subtitle="Povratak",
                       season=2, episode=5, episode_total=10)
    entries = (
        ScheduleEntry(at(19, 0), at(20, 55), "Dugi film", "Opis filma.", "Film", programme=film),
        ScheduleEntry(at(21, 0), at(21, 45), "Serijal", "Opis epizode.", "Serija", programme=series),
    )

    app, root, view = _build_app_view()
    try:
        app.schedule_service = StubSchedule(lambda channel: _outcome(channel, entries=entries))
        _select_rts1_serbia(view)
        assert _wait_until(lambda: "Učitavam" not in view.schedule_text)
        rows = list(reversed(view.ids.results.children))
        rows[0].dispatch("on_release")
        for _ in range(5):
            Clock.tick()
        dialog = view._details_dialog
        assert dialog is not None and dialog.title == "Dugi film"
        assert "FILM · 2019 · 1 h 55 min" in dialog.text
        assert "Režija: Reditelj Prvi" in dialog.text and dialog.text.endswith("Opis filma.")
        assert "RTS 1" in dialog.text

        rows[1].dispatch("on_release")  # drugi dijalog zamenjuje prvi
        for _ in range(5):
            Clock.tick()
        assert view._details_dialog is not dialog and view._details_dialog.title == "Serijal"
        assert "SERIJA · 45 min" in view._details_dialog.text
        assert "Sezona 2, epizoda 5 (od 10)" in view._details_dialog.text
        assert "Naslov epizode: Povratak" in view._details_dialog.text

        view.show_results()  # izlazak iz rasporeda zatvara dijalog
        assert view._details_dialog is None
    finally:
        Window.remove_widget(root)
