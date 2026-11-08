"""Testovi ekrana Podesavanja (Faza 7). Rade samo kad postoji ekran (na racunaru / xvfb)."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from test_smoke import (  # noqa: E402
    StubSchedule,
    _needs_display,
    _outcome,
    _select_rts1_serbia,
    _wait_until,
)


def _tick(times=5):
    from kivy.clock import Clock

    for _ in range(times):
        Clock.tick()


def _build():
    from kivy.core.window import Window
    from app.tvapp import TvProgramGlobalApp

    app = TvProgramGlobalApp()
    root = app.build()
    app.root = root
    Window.add_widget(root)
    _tick()
    return app, root, root.ids.search_view, root.ids.favourites_view, root.ids.settings_view


def _close(root):
    from kivy.core.window import Window

    Window.remove_widget(root)


def _options(settings_view):
    return [item.text for item in reversed(settings_view.ids.options.children)]


def test_settings_screen_lists_every_option_and_marks_the_current_ones():
    _needs_display()
    app, root, _search, _fav, settings = _build()
    try:
        texts = _options(settings)
        for expected in ("Srpski", "English", "Tamna", "Svetla", "24 sata (19:30)",
                         "12 sati (7:30 PM)", "Vreme stanice (preporučeno)",
                         "Vreme na mom uređaju", "Prema izvoru (preporučeno)",
                         "Samo ručno (dugme Osveži)"):
            assert expected in texts, expected
        tinted = [
            i.text for i in settings.ids.options.children
            if getattr(i, "bg_color", None) and i.bg_color[3] > 0.2
        ]
        assert sorted(tinted) == sorted([
            "Srpski", "Tamna", "24 sata (19:30)", "Vreme stanice (preporučeno)",
            "Prema izvoru (preporučeno)"])
        assert settings.note_text == ""  # trajno cuvanje radi
    finally:
        _close(root)


def test_language_switch_translates_every_screen_at_once():
    _needs_display()
    app, root, search, favourites, settings = _build()
    try:
        search.run_search("RTS 1")
        assert any("Srbija (RS)" in i.secondary_text for i in search.ids.results.children)

        settings._on_pick("language", "en")
        _tick()
        assert app.language == "en"
        assert any("Serbia (RS)" in i.secondary_text for i in search.ids.results.children)
        assert search.status_text.startswith("Channels found:")
        assert "No favourite channels" in favourites.status_text
        assert "English" in _options(settings) and "Dark" in _options(settings)
        assert "Build type:" in app.runtime_info
        assert app.t("tab_settings", app.language) == "Settings"
    finally:
        _close(root)


def test_language_switch_keeps_the_open_schedule_and_translates_it():
    _needs_display()
    app, root, search, _fav, settings = _build()
    try:
        app.schedule_service = StubSchedule(lambda channel: _outcome(channel))
        _select_rts1_serbia(search)
        assert _wait_until(lambda: "Učitavam" not in search.schedule_text)
        assert "Raspored: RTS 1 (Srbija)" in search.schedule_text

        settings._on_pick("language", "en")
        _tick()
        assert search.in_schedule
        assert "Schedule: RTS 1 (Serbia)" in search.schedule_text
        assert "Date: 2026-11-06" in search.schedule_text
        assert search.back_text == "Back to results"
    finally:
        _close(root)


def test_theme_switch_changes_colors_and_kivymd_style():
    _needs_display()
    from app.theme import PALETTES

    app, root, _search, _fav, settings = _build()
    try:
        assert app.theme_cls.theme_style == "Dark"
        settings._on_pick("theme", "light")
        _tick()
        assert app.theme_cls.theme_style == "Light"
        assert list(app.colors["navy"]) == PALETTES["light"]["navy"]
        assert list(root.md_bg_color) == PALETTES["light"]["navy"]
        settings._on_pick("theme", "dark")
        _tick()
        assert list(root.md_bg_color) == PALETTES["dark"]["navy"]
    finally:
        _close(root)


def test_time_format_changes_the_schedule_without_reloading_it():
    _needs_display()
    app, root, search, _fav, settings = _build()
    try:
        stub = StubSchedule(lambda channel: _outcome(channel))
        app.schedule_service = stub
        _select_rts1_serbia(search)
        assert _wait_until(lambda: "Učitavam" not in search.schedule_text)
        rows = [i.text for i in reversed(search.ids.results.children)]
        assert rows[0] == "19:30-20:00  Dnevnik"

        settings._on_pick("time_format", "12h")
        _tick()
        rows = [i.text for i in reversed(search.ids.results.children)]
        assert rows[0] == "7:30 PM-8:00 PM  Dnevnik"
        assert rows[1].startswith("8:00 PM  Film")
        assert stub.calls == ["RTS1.rs"]  # nije bilo novog preuzimanja
    finally:
        _close(root)


def test_device_time_zone_shows_the_zone_line_and_falls_back_when_unknown(monkeypatch):
    _needs_display()
    app, root, search, _fav, settings = _build()
    try:
        app.schedule_service = StubSchedule(lambda channel: _outcome(channel))
        _select_rts1_serbia(search)
        assert _wait_until(lambda: "Učitavam" not in search.schedule_text)

        monkeypatch.setattr("app.tvapp.detect_device_zone_name", lambda: "America/New_York")
        settings._on_pick("time_zone", "device")
        _tick()
        rows = [i.text for i in reversed(search.ids.results.children)]
        assert rows[0] == "13:30-14:00  Dnevnik"  # 19:30 CET = 13:30 EST (6.11.2026.)
        assert any("America/New_York" in w.text for w in settings.ids.options.children)

        monkeypatch.setattr("app.tvapp.detect_device_zone_name", lambda: None)
        app._device_zone = None
        app.ui_version += 1
        _tick()
        rows = [i.text for i in reversed(search.ids.results.children)]
        assert rows[0] == "19:30-20:00  Dnevnik"  # zona nije poznata: ostaje zona stanice
        assert any("nije prepoznata" in w.text for w in settings.ids.options.children)
    finally:
        _close(root)


def test_manual_refresh_setting_stops_automatic_downloads_but_not_the_button():
    _needs_display()
    app, root, search, _fav, settings = _build()
    try:
        stub = StubSchedule(lambda channel: _outcome(channel, "network_error"))
        app.schedule_service = stub
        settings._on_pick("refresh", "manual")
        _tick()
        _select_rts1_serbia(search)
        assert _wait_until(lambda: "Učitavam" not in search.schedule_text)
        stub.manual_only = True
        search._last_reload -= 400
        search._tick(0)
        assert stub.calls == ["RTS1.rs"]  # nema automatskog ponovnog preuzimanja
        search.refresh_schedule()
        assert _wait_until(lambda: len(stub.calls) == 2)
    finally:
        _close(root)


def test_settings_are_remembered_after_restart():
    _needs_display()
    from app.theme import PALETTES

    app, root, _search, _fav, settings = _build()
    try:
        settings._on_pick("language", "en")
        settings._on_pick("theme", "light")
        settings._on_pick("time_format", "12h")
        settings._on_pick("refresh", "24h")
    finally:
        _close(root)

    app2, root2, search2, _fav2, settings2 = _build()  # isti folder (conftest), novo pokretanje
    try:
        assert app2.language == "en"
        assert app2.theme_name == "light" and app2.theme_cls.theme_style == "Light"
        assert app2.setting("time_format") == "12h"
        assert app2.setting("refresh") == "24h"
        assert settings2.note_text == ""
        assert search2.status_text.startswith("Examples:")
        assert list(root2.md_bg_color) == PALETTES["light"]["navy"]
    finally:
        _close(root2)


def test_without_storage_settings_work_but_the_screen_says_they_are_not_saved(monkeypatch, tmp_path):
    _needs_display()
    blocker = tmp_path / "fajl"
    blocker.write_text("x")
    monkeypatch.setenv("TVPG_USER_DATA_DIR", str(blocker / "ne" / "moze"))
    app, root, _search, _fav, settings = _build()
    try:
        assert "ne mogu trajno sačuvati" in settings.note_text
        settings._on_pick("theme", "light")
        _tick()
        assert app.theme_name == "light"  # vazi do zatvaranja aplikacije
    finally:
        _close(root)


def test_time_range_uses_display_zone_for_yesterday_and_tomorrow_labels():
    pytest.importorskip("kivymd")
    import datetime
    from zoneinfo import ZoneInfo
    from app.screens.search_view import time_range
    from app.services.schedule_service import ScheduleEntry
    from app.strings import t as translate
    from app.utils.clockfmt import ClockFormat

    class _T:
        @staticmethod
        def t(key):
            return translate(key, "sr")

    belgrade, new_york = ZoneInfo("Europe/Belgrade"), ZoneInfo("America/New_York")
    entry = ScheduleEntry(
        datetime.datetime(2026, 11, 7, 3, 0, tzinfo=belgrade),
        datetime.datetime(2026, 11, 7, 4, 0, tzinfo=belgrade), "Nocni")
    # u stanici je ovo sutra, ali u Njujorku je jos 6.11. uvece
    assert time_range(_T, entry, datetime.date(2026, 11, 6), ClockFormat(False, new_york)) == "21:00-22:00"
    assert time_range(_T, entry, datetime.date(2026, 11, 6), ClockFormat(True, new_york)) == "9:00 PM-10:00 PM"
