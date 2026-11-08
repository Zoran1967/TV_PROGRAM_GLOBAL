"""Ekran podesavanja: jezik, tema, format i zona vremena, osvezavanje rasporeda."""

import logging
from functools import partial

from kivy.properties import StringProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.list import OneLineListItem

from app.services.settings_service import (
    DEFINITIONS,
    REFRESH,
    TIME_ZONE,
    option_label_key,
)

_LOGGER = logging.getLogger(__name__)

# Izabrana opcija je istaknuta bojom pozadine (isti zlatni ton kao "Sada" u rasporedu)
SELECTED_TINT = [0.85, 0.70, 0.25, 0.25]


def _fit_height(label, size):
    label.height = size[1]


def _label(text, **kwargs):
    """Tekst koji se prelama i sam odredjuje visinu (isto kao MDLabel u main.kv)."""
    label = MDLabel(text=text, size_hint_y=None, **kwargs)
    label.bind(texture_size=_fit_height)
    return label


class SettingsView(MDBoxLayout):
    note_text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._busy = False  # dok traje promena, ekran se crta tek na kraju
        self._save_failed = False

    def on_kv_post(self, base_widget):
        app = MDApp.get_running_app()
        app.bind(ui_version=self._on_settings_changed)
        self.rebuild()

    def _on_settings_changed(self, *_args):
        if not self._busy:
            self.rebuild()

    # ---- crtanje -----------------------------------------------------------------

    def rebuild(self):
        app = MDApp.get_running_app()
        service = app.settings_service
        box = self.ids.options
        box.clear_widgets()
        if service is None:
            return
        if not service.persistent:
            self.note_text = app.t("settings_not_saved")
        elif self._save_failed:
            self.note_text = app.t("settings_save_error")
        else:
            self.note_text = ""
        gold = app.colors["gold"]
        muted = app.colors["text_muted"]
        for definition in DEFINITIONS:
            current = service.get(definition.key)
            title = "%s: %s" % (
                app.t("setting_" + definition.key),
                app.t(option_label_key(definition.key, current)),
            )
            box.add_widget(_label(
                title, font_style="Subtitle1", theme_text_color="Custom", text_color=gold))
            for value in definition.options:
                box.add_widget(self._option_item(app, definition.key, value, value == current, gold))
            hint = self._hint(app, definition.key)
            if hint:
                box.add_widget(_label(hint, theme_text_color="Custom", text_color=muted))
        self._sync_tab_titles(app)

    def _option_item(self, app, key, value, selected, gold):
        item = OneLineListItem(text=app.t(option_label_key(key, value)))
        if selected:
            item.bg_color = SELECTED_TINT
            item.theme_text_color = "Custom"
            item.text_color = gold
        item.bind(on_release=partial(self._on_pick, key, value))
        return item

    @staticmethod
    def _hint(app, key):
        if key == TIME_ZONE:
            _zone, name = app.device_zone()
            if name:
                return app.t("time_zone_hint").format(zone=name)
            return app.t("time_zone_unknown")
        if key == REFRESH:
            return app.t("refresh_hint")
        return ""

    @staticmethod
    def _sync_tab_titles(app):
        """Naslovi kartica donje navigacije prate jezik (ako ih biblioteka sama ne osvezi)."""
        root = app.root
        if root is None:
            return
        try:
            for tab in root.ids.nav.ids.tab_manager.screens:
                header = getattr(tab, "header", None)
                if header is not None and hasattr(header, "text") and header.text != tab.text:
                    header.text = tab.text
        except Exception:  # samo ulepsavanje; ne sme da sruši ekran
            _LOGGER.debug("Naslovi kartica nisu osvezeni", exc_info=True)

    # ---- izbor -------------------------------------------------------------------

    def _on_pick(self, key, value, *_args):
        app = MDApp.get_running_app()
        service = app.settings_service
        if service is None or service.get(key) == value:
            return
        self._busy = True
        try:
            saved = app.set_setting(key, value)
        finally:
            self._busy = False
        self._save_failed = bool(service.persistent and not saved)
        self.rebuild()
