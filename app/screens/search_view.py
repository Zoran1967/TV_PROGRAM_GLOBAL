"""Ekran pretrage TV stanica i prikaz rasporeda izabrane stanice."""

import datetime
import logging
import threading
import time
from functools import partial

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivymd.app import MDApp
from kivymd.uix.button import MDFlatButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.list import OneLineListItem, TwoLineListItem
from kivymd.uix.scrollview import MDScrollView

from app.providers.errors import ZoneUnavailableError
from app.providers.xmltv import load_zone
from app.services.schedule_service import ScheduleOutcome, ScheduleStatus
from app.services.search_service import SearchStatus
from app.utils.clockfmt import ClockFormat, format_date
from app.utils.countries import country_name
from app.utils.details import build_details
from app.utils.text import normalize_text

DEBOUNCE_SECONDS = 0.3
TICK_SECONDS = 20
# Najcesce automatsko ponovno preuzimanje kada prikaz nije u redu (greska, istekli podaci)
RELOAD_COOLDOWN_SECONDS = 300
SEPARATOR = " \u00b7 "
DESCRIPTION_PREVIEW = 90
CURRENT_TINT = [0.85, 0.70, 0.25, 0.20]
NEXT_TINT = [0.85, 0.70, 0.25, 0.08]

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


# ---- formatiranje (bez Kivy-ja, lako za testiranje) -------------------------

_STATION_24H = ClockFormat()


def hhmm(value, fmt=None):
    """"19:30" (ili "7:30 PM" po podesavanju); bez fmt uvek 24-casovno u zoni vrednosti."""
    return (fmt or _STATION_24H).clock(value)


def format_age(app, seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return app.t("age_under_minute")
    minutes = seconds // 60
    if minutes < 60:
        return app.t("age_minutes").format(n=minutes)
    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return app.t("age_hours_only").format(h=hours)
    return app.t("age_hours").format(h=hours, m=rest)


def time_range(app, entry, local_date, fmt=None):
    """"19:30-20:00"; emisija koja je pocela juce ili se zavrsava sutra je oznacena.

    local_date je "danas" u zoni prikaza (fmt); bez fmt su to zona i datum stanice.
    """
    fmt = fmt or _STATION_24H
    start = fmt.clock(entry.start)
    if fmt.date_of(entry.start) < local_date:
        start = "%s %s" % (app.t("day_yesterday"), start)
    if entry.end is None:
        return start
    end = fmt.clock(entry.end)
    if fmt.date_of(entry.end) > local_date:
        end = "%s (%s)" % (end, app.t("day_tomorrow"))
    return "%s-%s" % (start, end)


class SearchView(MDBoxLayout):
    status_text = StringProperty("")
    schedule_text = StringProperty("")
    in_schedule = BooleanProperty(False)
    back_text = StringProperty("")
    favourite_icon = StringProperty("star-outline")
    favourites_enabled = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pending = None
        self._request_id = 0
        self._last_outcome = None  # poslednji rezultat pretrage
        self._channel = None
        self._origin = "search"  # odakle je otvoren raspored: "search" ili "favourites"
        self._sources = None
        self._outcome = None  # poslednji prikazani raspored
        self._signature = None
        self._tick_event = None
        self._last_reload = 0.0
        self._status = None  # (kljuc teksta, vrednosti) poslednje poruke, da se prevede kad se jezik promeni
        self._schedule_message = None  # kljuc poruke ispod naslova (ucitavanje, nema izvora, greska)
        self._fmt = ClockFormat()  # prikaz vremena za poslednje crtanje rasporeda

    def on_kv_post(self, base_widget):
        app = MDApp.get_running_app()
        self._set_status("search_examples")
        self.back_text = app.t("schedule_back")
        app.bind(ui_version=self._on_settings_changed)

    # ---- podesavanja: jezik, tema, format vremena --------------------------------

    def _set_status(self, key=None, **values):
        """Postavlja poruku iznad liste; pamti je da bi se prevela pri promeni jezika."""
        self._status = (key, values) if key else None
        self._show_status()

    def _show_status(self):
        app = MDApp.get_running_app()
        if self._status is None:
            self.status_text = ""
        else:
            key, values = self._status
            self.status_text = app.t(key).format(**values)

    def _on_settings_changed(self, *_args):
        """Ponovo crta prikaz sa novim jezikom, formatom vremena ili zonom (bez mreze)."""
        app = MDApp.get_running_app()
        self.back_text = app.t(
            "schedule_back_favourites" if self._origin == "favourites" else "schedule_back")
        if self.in_schedule:
            if self._outcome is not None:
                self._render(app, self._outcome)
            elif self._channel is not None and self._schedule_message:
                self._set_schedule_message(app, self._channel, self._schedule_message)
        elif self._last_outcome is not None:
            self._render_search(app, self._last_outcome)
        else:
            self._show_status()

    def _set_schedule_message(self, app, channel, key):
        """Naslov stanice i jedna poruka ispod njega (ucitavanje, nema izvora, greska)."""
        self._schedule_message = key
        self.schedule_text = "%s\n%s" % (self._title(app, channel), app.t(key))

    @staticmethod
    def _title(app, channel):
        return app.t("schedule_title").format(
            name=channel.name, country=country_name(channel, app.language))

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
            self._set_status("search_error")
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
            self._set_status("search_too_short")
        elif outcome.status == SearchStatus.NOT_FOUND:
            self._set_status("search_not_found")
        elif outcome.status == SearchStatus.CATALOG_ERROR:
            self._set_status("search_error")
        else:
            self._set_status("search_examples")

    def _show_results(self, app, outcome):
        count = len(outcome.results)
        key = "search_truncated" if outcome.truncated else "search_count"
        self._set_status(key, count=count)
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
        parts = ["%s (%s)" % (country_name(channel, app.language), channel.country_code)]
        if channel.network and channel.network.casefold() != channel.name.casefold():
            parts.append(channel.network)
        if normalize_text(result.matched_alias) != normalize_text(channel.name):
            parts.append(app.t("result_found_as").format(alias=result.matched_alias))
        if result.needs_id:
            parts.append(app.t("result_id").format(id=channel.catalog_id))
        return SEPARATOR.join(parts)

    # ---- raspored: otvaranje i preuzimanje -------------------------------------

    def _on_select(self, result, *_args):
        self.open_schedule(result.channel, origin="search")

    def open_schedule(self, channel, force=False, origin=None):
        app = MDApp.get_running_app()
        app.selected_channel = channel
        self._cancel_tick()
        self._request_id += 1
        if origin is not None:
            self._origin = origin
        self.back_text = app.t(
            "schedule_back_favourites" if self._origin == "favourites" else "schedule_back")
        self._channel, self._sources = channel, None
        self._sync_favourite()
        self._outcome, self._signature = None, None
        self.in_schedule = True
        self._set_status()
        self.ids.results.clear_widgets()

        service = app.schedule_service
        if channel.source_count == 0 or service is None:
            self._set_schedule_message(app, channel, "schedule_no_source")
            return
        try:
            self._sources = service.sources_for(channel)
        except Exception:  # greska baze ne sme da sruši aplikaciju
            _LOGGER.exception("Izvori stanice nisu procitani")
            self._set_schedule_message(app, channel, "schedule_error")
            return
        self._set_schedule_message(app, channel, "schedule_loading")
        self._start_load(service, force)

    def refresh_schedule(self):
        """Dugme "Osvezi": trazi nove podatke (servis ogranicava ucestalost)."""
        if self.in_schedule and self._channel is not None:
            self.open_schedule(self._channel, force=True, origin=self._origin)

    def _start_load(self, service, force):
        self._last_reload = time.time()
        threading.Thread(
            target=self._load,
            args=(self._request_id, service, self._channel, self._sources, force),
            daemon=True,
        ).start()

    def _load(self, request_id, service, channel, sources, force):
        """Radi u pozadinskoj niti: samo preuzima; ekran se menja u glavnoj niti."""
        try:
            outcome = service.get_schedule(channel, sources, force=force)
        except Exception as error:
            _LOGGER.exception("Raspored nije ucitan")
            outcome = ScheduleOutcome(ScheduleStatus.ERROR, channel, detail=str(error))
        Clock.schedule_once(lambda _dt: self.on_schedule_loaded(request_id, outcome))

    def on_schedule_loaded(self, request_id, outcome):
        if request_id != self._request_id or not self.in_schedule:
            return  # korisnik je u medjuvremenu izabrao drugu stanicu ili se vratio
        app = MDApp.get_running_app()
        self._outcome = outcome
        self._render(app, outcome)
        self._start_tick()

    # ---- raspored: prikaz --------------------------------------------------------

    def _render(self, app, outcome):
        """Crta zaglavlje i listu emisija."""
        self._schedule_message = None
        self._fmt = app.clock_format()
        self._signature = self._signature_of(outcome)
        self.schedule_text = self._header_text(app, outcome)
        results = self.ids.results
        results.clear_widgets()
        if outcome.status not in (ScheduleStatus.OK, ScheduleStatus.NO_DATA_FOR_DATE):
            return
        focus = None
        for entry in outcome.entries:
            item = self._entry_item(app, entry, outcome)
            results.add_widget(item)
            if focus is None and (entry.is_current or entry.is_next):
                focus = item
            if entry.gap_until is not None:
                results.add_widget(self._gap_item(app, entry))
        if focus is not None:
            Clock.schedule_once(lambda _dt: self._scroll_to(focus), 0.1)

    def _scroll_to(self, item):
        if item.parent is not None:
            self.ids.scroll.scroll_to(item, padding=dp(60), animate=False)

    @staticmethod
    def _signature_of(outcome):
        return (
            outcome.status, outcome.local_date, outcome.fetched_at, outcome.stale,
            outcome.current.start if outcome.current else None,
            outcome.next.start if outcome.next else None,
            len(outcome.entries),
        )

    def _header_text(self, app, outcome):
        self._fmt = app.clock_format()
        lines = [self._title(app, outcome.channel)]
        if outcome.status in (ScheduleStatus.OK, ScheduleStatus.NO_DATA_FOR_DATE):
            lines.extend(self._status_lines(app, outcome))
            if outcome.status == ScheduleStatus.NO_DATA_FOR_DATE:
                lines.append(app.t("schedule_no_data_date").format(
                    date=self._date(app, outcome.local_date)))
        elif outcome.status == ScheduleStatus.HTTP_ERROR:
            lines.append(self._http_message(app, outcome.http_status))
            lines.extend(self._license_note(app, outcome))
        else:
            lines.append(app.t(_STATUS_MESSAGES.get(outcome.status, "schedule_error")))
            lines.extend(self._license_note(app, outcome))
        return "\n".join(lines)

    def _status_lines(self, app, outcome):
        lines = [app.t("schedule_date_zone").format(
            date=self._date(app, outcome.local_date), zone=outcome.timezone,
            label=outcome.zone_label)]
        if outcome.now_local is not None:
            # Vreme u stanici ostaje u zoni stanice (samo se 12/24 h bira po podesavanju)
            lines.append(app.t("station_time").format(
                time=ClockFormat(self._fmt.hour12).clock(outcome.now_local),
                label=outcome.zone_label))
            if self._fmt.converts:
                lines.append(app.t("time_shown_in").format(
                    zone=app.device_zone()[1], label=self._fmt.zone_label(outcome.now_local)))
        lines.append(self._now_line(app, outcome))
        lines.append(self._next_line(app, outcome))
        lines.append(app.t("schedule_source").format(source=outcome.source_name))
        lines.extend(self._freshness_lines(app, outcome))
        lines.extend(self._license_note(app, outcome))
        return lines

    def _now_line(self, app, outcome):
        current = outcome.current
        if current is None or outcome.current_end is None or outcome.now_local is None:
            return app.t("now_none")
        left = (outcome.current_end - outcome.now_local).total_seconds()
        key = "now_line_derived" if outcome.current_end_derived else "now_line"
        return app.t(key).format(
            title=current.title, end=self._fmt.clock(outcome.current_end),
            left=self._left(app, left))

    def _left(self, app, seconds):
        minutes = int(seconds // 60)
        if minutes < 1:
            return app.t("left_under_minute")
        return format_age(app, minutes * 60)

    def _next_line(self, app, outcome):
        following = outcome.next
        if following is None:
            return app.t("next_none")
        key = "next_line"
        today = self._today(outcome)
        if today is not None and self._fmt.date_of(following.start) > today:
            key = "next_line_tomorrow"
        return app.t(key).format(title=following.title, time=self._fmt.clock(following.start))

    def _today(self, outcome):
        """"Danas" u zoni prikaza: datum stanice, ili datum uredjaja kad se vreme prikazuje po njemu."""
        if self._fmt.converts and outcome.now_local is not None:
            return self._fmt.date_of(outcome.now_local)
        return outcome.local_date

    def _freshness_lines(self, app, outcome):
        if outcome.stale:
            return [app.t("schedule_stale").format(reason=self._reason(app, outcome))]
        if outcome.fetched_at is None or outcome.now_local is None:
            return []
        zone = outcome.now_local.tzinfo
        fetched = datetime.datetime.fromtimestamp(outcome.fetched_at, zone)
        age = int(outcome.now_local.timestamp()) - outcome.fetched_at
        if outcome.refresh_seconds and age > outcome.refresh_seconds:
            return [app.t("fresh_old").format(
                age=format_age(app, age), time=self._fmt.clock(fetched))]
        return [app.t("fresh_ok").format(
            time=self._fmt.clock(fetched), age=format_age(app, age))]

    @staticmethod
    def _license_note(app, outcome):
        return [app.t("schedule_dev_note")] if outcome.license_status == "pending" else []

    @staticmethod
    def _date(app, value):
        return format_date(value, app.language)

    def _reason(self, app, outcome):
        if outcome.error_status == ScheduleStatus.HTTP_ERROR:
            return self._http_message(app, outcome.http_status)
        return app.t(_STATUS_MESSAGES.get(outcome.error_status, "schedule_error"))

    @staticmethod
    def _http_message(app, status):
        if status == 404:
            return app.t("schedule_http_404")
        return app.t("schedule_http_error").format(code=status)

    def _entry_item(self, app, entry, outcome):
        times = time_range(app, entry, self._today(outcome), self._fmt)
        label = ""
        if entry.is_current:
            label = app.t("label_now") + "  "
        elif entry.is_next:
            label = app.t("label_next") + "  "
        secondary = entry.category or ""
        if not secondary and entry.description:
            text = entry.description
            secondary = text if len(text) <= DESCRIPTION_PREVIEW else text[:DESCRIPTION_PREVIEW - 3] + "..."
        if entry.is_current and outcome.current_end is not None and outcome.now_local is not None:
            left = self._left(app, (outcome.current_end - outcome.now_local).total_seconds())
            progress = app.t("now_left_short").format(left=left)
            secondary = "%s%s%s" % (progress, SEPARATOR if secondary else "", secondary)
        item = TwoLineListItem(text="%s%s  %s" % (label, times, entry.title), secondary_text=secondary)
        item.bind(on_release=partial(self._show_details, entry, outcome))
        if entry.is_current:
            item.bg_color = CURRENT_TINT
        elif entry.is_next:
            item.bg_color = NEXT_TINT
        elif entry.is_past:
            item.theme_text_color = "Hint"
            item.secondary_theme_text_color = "Hint"
        return item

    # ---- detalji emisije (dodir na emisiju) ----------------------------------------

    def _show_details(self, entry, outcome, *_args):
        app = MDApp.get_running_app()
        when = time_range(app, entry, self._today(outcome), self._fmt)
        title, _kind, body = build_details(app.t, entry, when, outcome.channel.name)
        self._close_details()
        # MDDialog (KivyMD 1.2.0) ne pomera dugačak tekst: opis se stavlja u sopstveni klizni deo
        # ogranicene visine, a dugme "Zatvori" ostaje uvek na ekranu.
        dialog = MDDialog(
            title=title,
            text=body,  # ne prikazuje se (type="custom"), ali ostaje procitljiv kao dialog.text
            type="custom",
            content_cls=self._details_content(body),
            buttons=[MDFlatButton(
                text=app.t("detail_close"),
                theme_text_color="Custom",
                text_color=app.colors["gold"],
                on_release=lambda *_: self._close_details(),
            )],
        )
        self._details_dialog = dialog
        dialog.open()

    @staticmethod
    def _details_content(body):
        """Klizni tekst detalja: najvise ~50% visine ekrana, ceo opis se vidi skrolovanjem."""
        label = MDLabel(text=body, size_hint_y=None, halign="left", valign="top")
        label.bind(
            width=lambda widget, width: setattr(widget, "text_size", (width, None)),
            texture_size=lambda widget, size: setattr(widget, "height", size[1]),
        )
        scroll = MDScrollView(
            size_hint=(1, None),
            height=min(dp(420), Window.height * 0.5),
            do_scroll_x=False,
            bar_width=dp(4),
        )
        scroll.add_widget(label)
        return scroll

    def _close_details(self):
        dialog = getattr(self, "_details_dialog", None)
        self._details_dialog = None
        if dialog is not None:
            dialog.dismiss()

    def _gap_item(self, app, entry):
        item = OneLineListItem(text=app.t("schedule_gap").format(
            start=self._fmt.clock(entry.end), end=self._fmt.clock(entry.gap_until)))
        item.theme_text_color = "Hint"
        return item

    # ---- raspored: osvezavanje prikaza u toku vremena ----------------------------

    def _start_tick(self):
        if self._tick_event is None:
            self._tick_event = Clock.schedule_interval(self._tick, TICK_SECONDS)

    def _cancel_tick(self):
        if self._tick_event is not None:
            self._tick_event.cancel()
            self._tick_event = None

    def _tick(self, _dt):
        """Pomera "Sada/Sledece" i menja dan u ponoc, bez mreze; po potrebi trazi nove podatke."""
        app = MDApp.get_running_app()
        service = app.schedule_service
        if not self.in_schedule or self._channel is None or service is None or self._sources is None:
            return
        view = service.refresh_view(self._channel, self._sources)
        if view is None:
            self._maybe_reload(service)
            return
        previous = self._outcome
        self._outcome = view
        if self._signature_of(view) != self._signature:
            self._render(app, view)
        else:
            self.schedule_text = self._header_text(app, view)  # samo vreme i starost podataka
        needs_data = (
            view.status != ScheduleStatus.OK
            or (previous is not None and previous.status != ScheduleStatus.OK)
            or (view.refresh_seconds and view.now_local is not None and view.fetched_at is not None
                and view.now_local.timestamp() - view.fetched_at > view.refresh_seconds)
        )
        if needs_data:
            self._maybe_reload(service)

    def _maybe_reload(self, service):
        if getattr(service, "manual_only", False):
            return  # podesavanje "Samo ručno": novi podaci samo na dugme Osvezi
        if time.time() - self._last_reload >= RELOAD_COOLDOWN_SECONDS:
            self._request_id += 1
            self._start_load(service, False)

    def show_results(self):
        """Povratak sa rasporeda: na rezultate pretrage ili, ako je otvoren iz Omiljenih, na njih."""
        app = MDApp.get_running_app()
        came_from_favourites = self._origin == "favourites"
        self._leave_schedule()
        self.ids.results.clear_widgets()
        if self._last_outcome is not None:
            self._render_search(app, self._last_outcome)
        else:
            self._set_status("search_examples")
        if came_from_favourites:
            self._origin = "search"
            app.show_favourites_tab()

    # ---- omiljene ---------------------------------------------------------------

    def _sync_favourite(self):
        """Postavlja zvezdicu prema tome da li je izabrana stanica omiljena."""
        service = MDApp.get_running_app().favourites_service
        self.favourites_enabled = service is not None and self._channel is not None
        if not self.favourites_enabled:
            self.favourite_icon = "star-outline"
            return
        try:
            is_favourite = service.is_favourite(self._channel)
        except Exception:
            _LOGGER.exception("Stanje omiljene stanice nije procitano")
            self.favourites_enabled = False
            self.favourite_icon = "star-outline"
            return
        self.favourite_icon = "star" if is_favourite else "star-outline"

    def toggle_favourite(self):
        app = MDApp.get_running_app()
        service = app.favourites_service
        if service is None or self._channel is None:
            return
        try:
            service.toggle(self._channel)
        except Exception:  # greska baze ne sme da sruši aplikaciju
            _LOGGER.exception("Omiljena stanica nije sacuvana")
            self._set_status("fav_error")
            return
        self._set_status()
        self._sync_favourite()
        app.favourites_changed()

    def _leave_schedule(self):
        self._close_details()
        self._cancel_tick()
        self._request_id += 1  # odgovor koji tek stize vise se ne prikazuje
        self.in_schedule = False
        self.schedule_text = ""
        self._schedule_message = None
        self._channel = self._sources = self._outcome = self._signature = None
        self._sync_favourite()
