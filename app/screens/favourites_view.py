"""Ekran omiljenih stanica (grupisane po drzavama, svaka sa zvezdicom)."""

import logging
from functools import partial

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.list import IconLeftWidget, TwoLineAvatarIconListItem

from app.utils.chunked import ChunkedFiller, sync_mode
from app.utils.countries import country_name

_LOGGER = logging.getLogger(__name__)
SEPARATOR = " \u00b7 "
CONFIRM_SECONDS = 5  # koliko dugo vazi "dodirnite ponovo" za brisanje svih
POLL_SECONDS = 0.3  # koliko cesto se proverava da li je ekran Omiljenih postao vidljiv


def channel_secondary(channel, language="sr"):
    """Druga linija stanice: drzava (i mreza, ako se razlikuje od naziva)."""
    parts = ["%s (%s)" % (country_name(channel, language), channel.country_code)]
    if channel.network and channel.network.casefold() != channel.name.casefold():
        parts.append(channel.network)
    return SEPARATOR.join(parts)


def group_by_country(channels, language):
    """[(naziv drzave za prikaz, [stanice])]: drzave po abecedi, stanice po nazivu."""
    groups = {}
    for channel in channels:
        groups.setdefault(country_name(channel, language), []).append(channel)
    return [
        (name, sorted(items, key=lambda c: (c.name.casefold(), c.catalog_id)))
        for name, items in sorted(groups.items(), key=lambda pair: pair[0].casefold())
    ]


class CountryHeader(MDLabel):
    """Naslov grupe: odavde pocinje jedna drzava. Nije dugme."""


class FavouriteItem(TwoLineAvatarIconListItem):
    """Omiljena stanica (sa zvezdicom levo)."""


class FavouritesView(MDBoxLayout):
    status_text = StringProperty("")
    add_all_text = StringProperty("")
    clear_text = StringProperty("")
    can_add_all = BooleanProperty(False)
    can_clear = BooleanProperty(False)

    def on_kv_post(self, base_widget):
        app = MDApp.get_running_app()
        app.bind(favourites_version=self._on_version)
        app.bind(ui_version=self._on_version)  # promena jezika
        self._confirm_event = None
        self._filler = ChunkedFiller()
        self._signature = None  # po cemu je napravljen spisak na ekranu (jezik, tema, stanice)
        self._dirty = False
        self._poll_event = None
        self._request_refresh()

    def _on_version(self, *_args):
        self._request_refresh()

    def _request_refresh(self):
        """Spisak se pravi samo dok je ekran Omiljenih vidljiv.

        Dodir na zvezdicu na drugom ekranu ranije je odmah pravio ponovo sve stavke (stotinak
        KivyMD stavki, desetak sekundi) iako se ekran ne vidi, pa Android javi "ne reaguje".
        Ako ekran nije vidljiv, samo se pamti da je spisak zastareo; pravi se kad se prikaze.
        """
        if sync_mode() or self.get_root_window() is not None:
            self.refresh()
            return
        self._dirty = True
        if self._poll_event is None:
            self._poll_event = Clock.schedule_interval(self._poll, POLL_SECONDS)

    def _poll(self, _dt):
        if self.get_root_window() is None:
            return
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None
        if self._dirty:
            self.refresh()

    # ---- spisak ----------------------------------------------------------------

    def _clear_list(self):
        self._filler.cancel()
        self._signature = None
        self.ids.results.clear_widgets()

    def refresh(self):
        app = MDApp.get_running_app()
        self._dirty = False
        self._reset_confirm()
        service = app.favourites_service
        if service is None:
            self._clear_list()
            self._update_buttons(app, favourites=0)
            self.status_text = app.t("favourites_unavailable")
            return
        try:
            result = service.list_channels()
        except Exception:  # greska baze ne sme da sruši aplikaciju
            _LOGGER.exception("Omiljene stanice nisu procitane")
            self._clear_list()
            self._update_buttons(app, favourites=0)
            self.status_text = app.t("favourites_error")
            return
        self._update_buttons(app, favourites=len(result.channels) + result.missing)
        lines = []
        if result.channels:
            lines.append(app.t("favourites_count").format(count=len(result.channels)))
            lines.append(app.t("favourites_hint"))
        else:
            lines.append(app.t("favourites_empty"))
        if result.missing:
            lines.append(app.t("favourites_missing").format(count=result.missing))
        self.status_text = "\n".join(lines)
        # Ako se nista nije promenilo (isti jezik, tema i stanice), lista na ekranu ostaje netaknuta
        signature = (
            app.language, str(app.colors["gold"]), str(app.colors["navy_light"]),
            tuple(channel.catalog_id for channel in result.channels),
        )
        if signature == self._signature:
            return
        self._clear_list()
        self._signature = signature
        groups = group_by_country(result.channels, app.language)
        self._filler.fill(self.ids.results, self._builders(app, groups))

    def _builders(self, app, groups):
        for country, channels in groups:
            yield partial(self._header, app, country, len(channels))
            for channel in channels:
                yield partial(self._item, app, channel)

    @staticmethod
    def _header(app, country, count):
        header = CountryHeader(
            text=app.t("favourites_group").format(country=country, count=count),
            font_style="Subtitle1",
            bold=True,
            theme_text_color="Custom",
            text_color=app.colors["gold"],
            size_hint_y=None,
            height=dp(40),
            halign="left",
            valign="middle",
            padding=(dp(16), 0),
        )
        header.bind(size=lambda widget, size: setattr(widget, "text_size", size))
        header.md_bg_color = app.colors["navy_light"]  # tek posle pravljenja (canvas mora da postoji)
        return header

    def _item(self, app, channel):
        item = FavouriteItem(text=channel.name, secondary_text=channel_secondary(channel, app.language))
        item.add_widget(IconLeftWidget(
            icon="star", theme_icon_color="Custom", icon_color=app.colors["gold"]))
        item.bind(on_release=partial(self._on_select, channel))
        return item

    @staticmethod
    def _on_select(channel, *_args):
        MDApp.get_running_app().open_channel_schedule(channel, origin="favourites")

    # ---- dugmad: dodaj sve / ukloni sve ----------------------------------------------

    def _update_buttons(self, app, favourites):
        available = self._schedule_channels(app, quiet=True)
        self.add_all_text = app.t("fav_add_all").format(count=len(available))
        self.can_add_all = bool(available) and app.favourites_service is not None
        self.clear_text = app.t("fav_clear")
        self.can_clear = favourites > 0

    @staticmethod
    def _schedule_channels(app, quiet=False):
        """Stanice za koje aplikacija zna da cita raspored (greska = prazan spisak)."""
        service = app.schedule_service
        if service is None:
            return []
        try:
            return list(service.channels_with_schedule())
        except Exception:
            if not quiet:
                _LOGGER.exception("Spisak stanica sa rasporedom nije procitan")
            return []

    def add_all(self):
        """Dodaje u omiljene sve stanice sa rasporedom; vec dodate se ne dupliraju."""
        app = MDApp.get_running_app()
        service = app.favourites_service
        channels = self._schedule_channels(app)
        if service is None or not channels:
            return
        try:
            added = service.add_channels(channels)
        except Exception:
            _LOGGER.exception("Omiljene stanice nisu sacuvane")
            self.status_text = app.t("fav_error")
            return
        app.favourites_changed()  # osvezava spisak (i ovaj ekran)
        notice = app.t("favourites_added").format(added=added, already=len(channels) - added)
        self.status_text = "%s\n%s" % (notice, self.status_text)

    def clear_all(self):
        """Uklanja sve omiljene, ali tek na drugi dodir u roku od nekoliko sekundi."""
        app = MDApp.get_running_app()
        service = app.favourites_service
        if service is None or not self.can_clear:
            return
        if self._confirm_event is None:
            self.clear_text = app.t("fav_clear_confirm")
            self._confirm_event = Clock.schedule_once(self._expire_confirm, CONFIRM_SECONDS)
            return
        self._reset_confirm()
        try:
            removed = service.clear()
        except Exception:
            _LOGGER.exception("Omiljene stanice nisu uklonjene")
            self.status_text = app.t("fav_error")
            return
        app.favourites_changed()
        self.status_text = "%s\n%s" % (app.t("favourites_cleared").format(count=removed), self.status_text)

    def _expire_confirm(self, _dt):
        self._confirm_event = None
        self.clear_text = MDApp.get_running_app().t("fav_clear")

    def _reset_confirm(self):
        event = getattr(self, "_confirm_event", None)
        if event is not None:
            event.cancel()
        self._confirm_event = None
