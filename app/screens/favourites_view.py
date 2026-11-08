"""Ekran omiljenih stanica."""

import logging
from functools import partial

from kivy.properties import StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.list import TwoLineListItem

from app.utils.countries import country_name

_LOGGER = logging.getLogger(__name__)
SEPARATOR = " \u00b7 "


def channel_secondary(channel, language="sr"):
    """Druga linija stanice: drzava (i mreza, ako se razlikuje od naziva)."""
    parts = ["%s (%s)" % (country_name(channel, language), channel.country_code)]
    if channel.network and channel.network.casefold() != channel.name.casefold():
        parts.append(channel.network)
    return SEPARATOR.join(parts)


class FavouritesView(MDBoxLayout):
    status_text = StringProperty("")

    def on_kv_post(self, base_widget):
        app = MDApp.get_running_app()
        app.bind(favourites_version=self._on_version)
        app.bind(ui_version=self._on_version)  # promena jezika
        self.refresh()

    def _on_version(self, *_args):
        self.refresh()

    def refresh(self):
        app = MDApp.get_running_app()
        self.ids.results.clear_widgets()
        service = app.favourites_service
        if service is None:
            self.status_text = app.t("favourites_unavailable")
            return
        try:
            result = service.list_channels()
        except Exception:  # greska baze ne sme da sruši aplikaciju
            _LOGGER.exception("Omiljene stanice nisu procitane")
            self.status_text = app.t("favourites_error")
            return
        lines = []
        if result.channels:
            lines.append(app.t("favourites_count").format(count=len(result.channels)))
            lines.append(app.t("favourites_hint"))
        else:
            lines.append(app.t("favourites_empty"))
        if result.missing:
            lines.append(app.t("favourites_missing").format(count=result.missing))
        self.status_text = "\n".join(lines)
        for channel in result.channels:
            item = TwoLineListItem(text=channel.name, secondary_text=channel_secondary(channel, app.language))
            item.bind(on_release=partial(self._on_select, channel))
            self.ids.results.add_widget(item)

    @staticmethod
    def _on_select(channel, *_args):
        MDApp.get_running_app().open_channel_schedule(channel, origin="favourites")
