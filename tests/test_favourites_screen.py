"""Testovi ekrana omiljenih (Faza 6). Rade samo kad postoji ekran (na racunaru / xvfb)."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _needs_display():
    pytest.importorskip("kivymd")
    if not os.environ.get("DISPLAY") and not os.environ.get("KIVY_GL_BACKEND"):
        pytest.skip("nema ekrana za Kivy prozor")
    os.environ.setdefault("KIVY_NO_ARGS", "1")


def _tick(times=5):
    from kivy.clock import Clock

    for _ in range(times):
        Clock.tick()


def _build(keep_schedule=False):
    from kivy.core.window import Window
    from app.tvapp import TvProgramGlobalApp

    app = TvProgramGlobalApp()
    root = app.build()
    app.root = root  # run() radi isto posle build()
    Window.add_widget(root)
    _tick()
    if not keep_schedule:
        app.schedule_service = None  # bez mreze: raspored se ne preuzima, ostaje poruka "nema izvora"
    # Neaktivne kartice nisu u stablu prozora, pa se ekrani traze preko id-eva iz main.kv
    return app, root, root.ids.search_view, root.ids.favourites_view


def _close(root):
    from kivy.core.window import Window

    Window.remove_widget(root)


def _rows(view):
    """Stanice na ekranu omiljenih, od vrha ka dnu (bez naslova drzava)."""
    from app.screens.favourites_view import FavouriteItem

    return [w for w in reversed(view.ids.results.children) if isinstance(w, FavouriteItem)]


def _headers(view):
    from app.screens.favourites_view import CountryHeader

    return [w.text for w in reversed(view.ids.results.children) if isinstance(w, CountryHeader)]


def _open_rts1_serbia(view):
    view.run_search("RTS 1")
    item = next(i for i in view.ids.results.children
                if i.text == "RTS 1" and "Srbija" in i.secondary_text)
    item.dispatch("on_release")
    _tick()


def _current_tab(root):
    return root.ids.nav.ids.tab_manager.current


def test_favourite_star_adds_lists_and_removes():
    _needs_display()
    app, root, search, favourites = _build()
    try:
        assert _rows(favourites) == []
        assert "Nema omiljenih" in favourites.status_text

        _open_rts1_serbia(search)
        assert search.favourites_enabled is True
        assert search.favourite_icon == "star-outline"

        search.toggle_favourite()
        _tick()
        assert search.favourite_icon == "star"
        names = [i.text for i in _rows(favourites)]
        assert names == ["RTS 1"]
        assert "Srbija" in _rows(favourites)[0].secondary_text
        assert "Omiljenih stanica: 1" in favourites.status_text

        search.toggle_favourite()
        _tick()
        assert search.favourite_icon == "star-outline"
        assert _rows(favourites) == []
    finally:
        _close(root)


def test_favourites_persist_after_app_restart():
    _needs_display()
    app, root, search, favourites = _build()
    try:
        _open_rts1_serbia(search)
        search.toggle_favourite()
    finally:
        _close(root)

    app2, root2, search2, favourites2 = _build()  # ista promenljiva TVPG_USER_DATA_DIR = ista baza
    try:
        assert [i.text for i in _rows(favourites2)] == ["RTS 1"]
        _open_rts1_serbia(search2)
        assert search2.favourite_icon == "star"  # zvezdica je vec upaljena
    finally:
        _close(root2)


def test_tapping_favourite_opens_schedule_and_back_returns_to_favourites():
    _needs_display()
    app, root, search, favourites = _build()
    try:
        _open_rts1_serbia(search)
        search.toggle_favourite()
        search.show_results()
        _tick()

        _rows(favourites)[0].dispatch("on_release")
        _tick()
        assert _current_tab(root) == "search"
        assert search.in_schedule is True
        assert app.selected_channel.name == "RTS 1"
        assert search.back_text == "Nazad na omiljene"
        assert search.favourite_icon == "star"

        search.show_results()
        _tick()
        assert search.in_schedule is False
        assert _current_tab(root) == "favourites"
    finally:
        _close(root)


def test_opening_from_search_after_favourites_uses_search_back_button():
    _needs_display()
    app, root, search, favourites = _build()
    try:
        _open_rts1_serbia(search)
        search.toggle_favourite()
        search.show_results()
        _rows(favourites)[0].dispatch("on_release")
        search.show_results()
        _tick()
        root.ids.nav.switch_tab("search")  # korisnik se vraca na Pretragu
        _tick()
        _open_rts1_serbia(search)  # sada iz pretrage
        assert search.back_text == "Nazad na rezultate"
        search.show_results()
        _tick()
        assert _current_tab(root) == "search"  # ostaje na pretrazi, ne skace na omiljene
    finally:
        _close(root)


def test_without_storage_favourites_are_explained_and_star_is_hidden(monkeypatch, tmp_path):
    _needs_display()
    blocker = tmp_path / "fajl"
    blocker.write_text("x")
    monkeypatch.setenv("TVPG_USER_DATA_DIR", str(blocker / "ne" / "moze"))
    app, root, search, favourites = _build()
    try:
        assert app.favourites_service is None
        assert "nisu dostupne" in favourites.status_text
        _open_rts1_serbia(search)
        assert search.favourites_enabled is False
        search.toggle_favourite()  # ne baca gresku
        assert "nedostupno" in app.runtime_info
    finally:
        _close(root)


def test_store_error_on_toggle_is_shown_and_does_not_crash():
    _needs_display()
    app, root, search, favourites = _build()
    try:
        _open_rts1_serbia(search)

        class Broken:
            def is_favourite(self, channel):
                return False

            def toggle(self, channel):
                raise RuntimeError("disk pun")

        app.favourites_service = Broken()
        search.toggle_favourite()
        assert "nisu sačuvane" in search.status_text
        assert search.favourite_icon == "star-outline"
    finally:
        _close(root)


def test_add_all_puts_every_channel_with_schedule_in_favourites_grouped_by_country():
    _needs_display()
    app, root, search, favourites = _build(keep_schedule=True)
    try:
        expected = app.schedule_service.channels_with_schedule()
        assert len(expected) > 100                      # Balkan: 126 stanica u ugradjenom katalogu
        assert favourites.can_add_all and "(%d)" % len(expected) in favourites.add_all_text
        assert _rows(favourites) == []

        favourites.add_all()
        _tick()
        rows = _rows(favourites)
        assert len(rows) == len(expected)
        assert f"Dodato novih: {len(expected)}. Već su bile omiljene: 0." in favourites.status_text

        # drzave po abecedi, svaka pocinje naslovom sa brojem stanica
        headers = _headers(favourites)
        assert headers == sorted(headers, key=str.casefold)
        assert any(h.startswith("Srbija") for h in headers)
        children = list(reversed(favourites.ids.results.children))
        from app.screens.favourites_view import CountryHeader
        assert isinstance(children[0], CountryHeader)       # lista pocinje naslovom drzave
        serbia_at = next(i for i, w in enumerate(children) if isinstance(w, CountryHeader) and w.text.startswith("Srbija"))
        assert all(not isinstance(w, CountryHeader) for w in children[serbia_at + 1:serbia_at + 44])

        # drugi put se nista ne duplira
        favourites.add_all()
        _tick()
        assert len(_rows(favourites)) == len(expected)
        assert f"Dodato novih: 0. Već su bile omiljene: {len(expected)}." in favourites.status_text
    finally:
        _close(root)


def test_clear_all_needs_a_second_tap_and_removes_everything():
    _needs_display()
    app, root, search, favourites = _build(keep_schedule=True)
    try:
        assert favourites.can_clear is False
        favourites.add_all()
        _tick()
        assert favourites.can_clear is True
        total = len(_rows(favourites))

        favourites.clear_all()                          # prvi dodir samo trazi potvrdu
        assert "ponovo" in favourites.clear_text and len(_rows(favourites)) == total
        favourites.clear_all()                          # drugi dodir brise
        _tick()
        assert _rows(favourites) == [] and favourites.can_clear is False
        assert f"Uklonjeno omiljenih stanica: {total}." in favourites.status_text
        assert favourites.clear_text == "Ukloni sve omiljene"
    finally:
        _close(root)


def test_add_all_is_disabled_without_storage_or_schedule_source(monkeypatch, tmp_path):
    _needs_display()
    blocker = tmp_path / "fajl"
    blocker.write_text("x")
    monkeypatch.setenv("TVPG_USER_DATA_DIR", str(blocker / "ne" / "moze"))
    app, root, search, favourites = _build()
    try:
        assert favourites.can_add_all is False and favourites.can_clear is False
        favourites.add_all()                            # ne baca gresku
        favourites.clear_all()
    finally:
        _close(root)
