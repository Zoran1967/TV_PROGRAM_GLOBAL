"""Ekran pretrage TV stanica."""

import time
from functools import partial

from kivy.clock import Clock
from kivy.logger import Logger
from kivy.properties import StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.list import TwoLineListItem

from app.services.search_service import SearchStatus
from app.utils.text import normalize_text

DEBOUNCE_SECONDS = 0.3
SEPARATOR = " \u00b7 "


class SearchView(MDBoxLayout):
    status_text = StringProperty("")
    selected_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pending = None

    def on_kv_post(self, base_widget):
        self.status_text = MDApp.get_running_app().t("search_examples")

    def schedule_search(self, text):
        """Pokrece pretragu tek kada korisnik na kratko prestane da kuca."""
        if self._pending is not None:
            self._pending.cancel()
        self._pending = Clock.schedule_once(
            lambda _dt: self.run_search(text), DEBOUNCE_SECONDS
        )

    def run_search(self, text):
        app = MDApp.get_running_app()
        self.ids.results.clear_widgets()
        self.selected_text = ""
        service = app.search_service
        if service is None:
            self.status_text = app.t("search_error")
            return

        started = time.perf_counter()
        outcome = service.search(text)
        elapsed_ms = (time.perf_counter() - started) * 1000
        Logger.info("TVPG: pretraga %r: %s, %d rez, %.1f ms",
                    text, outcome.status.value, len(outcome.results), elapsed_ms)

        if outcome.status == SearchStatus.OK:
            self._show_results(app, outcome)
        elif outcome.status == SearchStatus.TOO_SHORT:
            self.status_text = app.t("search_too_short")
        elif outcome.status == SearchStatus.NOT_FOUND:
            self.status_text = app.t("search_not_found")
        elif outcome.status == SearchStatus.CATALOG_ERROR:
            self.status_text = app.t("search_error")
        else:
            self.status_text = app.t("search_examples")

    def _show_results(self, app, outcome):
        count = len(outcome.results)
        if outcome.truncated:
            self.status_text = app.t("search_truncated").format(count=count)
        else:
            self.status_text = app.t("search_count").format(count=count)
        for result in outcome.results:
            item = TwoLineListItem(
                text=result.channel.name,
                secondary_text=self._secondary_text(app, result),
            )
            item.bind(on_release=partial(self._on_select, result))
            self.ids.results.add_widget(item)

    @staticmethod
    def _secondary_text(app, result):
        channel = result.channel
        parts = ["%s (%s)" % (channel.country_name, channel.country_code)]
        if channel.network and channel.network.casefold() != channel.name.casefold():
            parts.append(channel.network)
        if normalize_text(result.matched_alias) != normalize_text(channel.name):
            parts.append(app.t("result_found_as").format(alias=result.matched_alias))
        if result.needs_id:
            parts.append(app.t("result_id").format(id=channel.catalog_id))
        return SEPARATOR.join(parts)

    def _on_select(self, result, *_args):
        app = MDApp.get_running_app()
        app.selected_channel = result.channel
        self.selected_text = "%s\n%s" % (
            app.t("selected_label").format(
                name=result.channel.name, country=result.channel.country_name
            ),
            app.t("selected_note"),
        )
