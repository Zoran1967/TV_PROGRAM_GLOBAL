"""Ekran pretrage TV stanica i prikaz rasporeda izabrane stanice."""

import datetime
import logging
import threading
import time
from functools import partial

from kivy.clock import Clock
from kivy.logger import Logger
from kivy.properties import BooleanProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.list import TwoLineListItem

from app.providers.xmltv import load_zone
from app.providers.errors import ZoneUnavailableError
from app.services.schedule_service import ScheduleOutcome, ScheduleStatus
from app.services.search_service import SearchStatus
from app.utils.text import normalize_text

DEBOUNCE_SECONDS = 0.3
SEPARATOR = " \u00b7 "
DESCRIPTION_PREVIEW = 90

_LOGGER = logging.getLogger(__name__)

_STATUS_MESSAGES = {
    ScheduleStatus.NETWORK_ERROR: "schedule_net_error",
    ScheduleStatus.RATE_LIMITED: "schedule_rate_limited",
    ScheduleStatus.EMPTY: "schedule_empty",
    ScheduleStatus.PARSE_ERROR: "schedule_parse_error",
    ScheduleStatus.ZONE_UNAVAILABLE: "schedule_zone_error",
    ScheduleStatus.NO_SOURCE: "schedule_no_source",
    ScheduleStatus.SOURCE_UNAVAILABLE: "schedule_unavailable",
    ScheduleStatus.ERROR: "schedule_error",
}


class SearchView(MDBoxLayout):
    status_text = StringProperty("")
    schedule_text = StringProperty("")
    in_schedule = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pending = None
        self._request_id = 0
        self._last_outcome = None

    def on_kv_post(self, base_widget):
        self.status_text = MDApp.get_running_app().t("search_examples")

    # ---- pretraga ---------------------------------------------------------

    def schedule_search(self, text):
        """Pokrece pretragu tek kada korisnik na kratko prestane da kuca."""
        if self._pending is not None:
            self._pending.cancel()
        self._pending = Clock.schedule_once(
            lambda _dt: self.run_search(text), DEBOUNCE_SECONDS
        )

    def run_search(self, text):
        app = MDApp.get_running_app()
        self._leave_schedule()
        self.ids.results.clear_widgets()
        self._last_outcome = None
        service = app.search_service
        if service is None:
            self.status_text = app.t("search_error")
            return

        started = time.perf_counter()
        outcome = service.search(text)
        elapsed_ms = (time.perf_counter() - started) * 1000
        Logger.info("TVPG: pretraga %r: %s, %d rez, %.1f ms",
                    text, outcome.status.value, len(outcome.results), elapsed_ms)
        self._last_outcome = outcome
        self._render_search(app, outcome)

    def _render_search(self, app, outcome):
        self.ids.results.clear_widgets()
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
        key = "search_truncated" if outcome.truncated else "search_count"
        self.status_text = app.t(key).format(count=count)
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

    # ---- raspored ---------------------------------------------------------

    def _on_select(self, result, *_args):
        self.open_schedule(result.channel)

    def open_schedule(self, channel):
        app = MDApp.get_running_app()
        app.selected_channel = channel
        self._request_id += 1
        request_id = self._request_id
        self.in_schedule = True
        self.status_text = ""
        self.ids.results.clear_widgets()
        title = app.t("schedule_title").format(name=channel.name, country=channel.country_name)

        service = app.schedule_service
        if channel.source_count == 0 or service is None:
            self.schedule_text = "%s\n%s" % (title, app.t("schedule_no_source"))
            return
        try:
            sources = service.sources_for(channel)
        except Exception:  # greska baze ne sme da sruši aplikaciju
            _LOGGER.exception("Izvori stanice nisu procitani")
            self.schedule_text = "%s\n%s" % (title, app.t("schedule_error"))
            return
        self.schedule_text = "%s\n%s" % (title, app.t("schedule_loading"))
        threading.Thread(
            target=self._load, args=(request_id, service, channel, sources), daemon=True
        ).start()

    def _load(self, request_id, service, channel, sources):
        """Radi u pozadinskoj niti: samo preuzima; ekran se menja u glavnoj niti."""
        try:
            outcome = service.get_schedule(channel, sources)
        except Exception as error:
            _LOGGER.exception("Raspored nije ucitan")
            outcome = ScheduleOutcome(ScheduleStatus.ERROR, channel, detail=str(error))
        Clock.schedule_once(lambda _dt: self.on_schedule_loaded(request_id, outcome))

    def on_schedule_loaded(self, request_id, outcome):
        if request_id != self._request_id or not self.in_schedule:
            return  # korisnik je u medjuvremenu izabrao drugu stanicu ili se vratio
        app = MDApp.get_running_app()
        channel = outcome.channel
        lines = [app.t("schedule_title").format(name=channel.name, country=channel.country_name)]
        self.ids.results.clear_widgets()

        if outcome.status in (ScheduleStatus.OK, ScheduleStatus.NO_DATA_FOR_DATE):
            lines.extend(self._header_lines(app, outcome))
            if outcome.status == ScheduleStatus.NO_DATA_FOR_DATE:
                lines.append(app.t("schedule_no_data_date").format(date=self._date(outcome.local_date)))
            for entry in outcome.entries:
                self.ids.results.add_widget(self._entry_item(entry))
        elif outcome.status == ScheduleStatus.HTTP_ERROR:
            lines.append(self._http_message(app, outcome.http_status))
            lines.extend(self._source_note(app, outcome))
        else:
            lines.append(app.t(_STATUS_MESSAGES.get(outcome.status, "schedule_error")))
            lines.extend(self._source_note(app, outcome))
        self.schedule_text = "\n".join(lines)

    def _header_lines(self, app, outcome):
        lines = [
            app.t("schedule_date_zone").format(
                date=self._date(outcome.local_date),
                zone=outcome.timezone, label=outcome.zone_label,
            ),
            app.t("schedule_source").format(
                source=outcome.source_name, time=self._fetched_time(outcome)),
        ]
        if outcome.stale:
            lines.append(app.t("schedule_stale").format(reason=self._reason(app, outcome)))
        lines.extend(self._license_note(app, outcome))
        return lines

    @staticmethod
    def _license_note(app, outcome):
        return [app.t("schedule_dev_note")] if outcome.license_status == "pending" else []

    def _source_note(self, app, outcome):
        return self._license_note(app, outcome)

    @staticmethod
    def _date(value):
        return value.strftime("%d.%m.%Y.") if value else ""

    @staticmethod
    def _fetched_time(outcome):
        if outcome.fetched_at is None:
            return ""
        try:
            zone = load_zone(outcome.timezone)
        except ZoneUnavailableError:
            return ""
        return datetime.datetime.fromtimestamp(outcome.fetched_at, zone).strftime("%H:%M")

    def _reason(self, app, outcome):
        if outcome.error_status == ScheduleStatus.HTTP_ERROR:
            return self._http_message(app, outcome.http_status)
        return app.t(_STATUS_MESSAGES.get(outcome.error_status, "schedule_error"))

    @staticmethod
    def _http_message(app, status):
        if status == 404:
            return app.t("schedule_http_404")
        return app.t("schedule_http_error").format(code=status)

    @staticmethod
    def _entry_item(entry):
        times = entry.start.strftime("%H:%M")
        if entry.end is not None:
            times += "-" + entry.end.strftime("%H:%M")
        secondary = entry.category or ""
        if not secondary and entry.description:
            text = entry.description
            secondary = text if len(text) <= DESCRIPTION_PREVIEW else text[:DESCRIPTION_PREVIEW - 3] + "..."
        return TwoLineListItem(text="%s  %s" % (times, entry.title), secondary_text=secondary)

    def show_results(self):
        """Povratak sa rasporeda na rezultate pretrage."""
        app = MDApp.get_running_app()
        self._leave_schedule()
        self.ids.results.clear_widgets()
        if self._last_outcome is not None:
            self._render_search(app, self._last_outcome)
        else:
            self.status_text = app.t("search_examples")

    def _leave_schedule(self):
        self._request_id += 1  # odgovor koji tek stize vise se ne prikazuje
        self.in_schedule = False
        self.schedule_text = ""
