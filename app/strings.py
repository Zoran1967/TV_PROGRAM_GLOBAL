"""Tekstovi interfejsa. Pocetni jezik je srpski.

Novi jezik se dodaje kao novi recnik u STRINGS (Faza 7).
"""

DEFAULT_LANGUAGE = "sr"

STRINGS = {
    "sr": {
        "app_title": "TV Program Global",
        "tab_search": "Pretraga",
        "tab_favourites": "Omiljeni",
        "tab_settings": "Podešavanja",
        "search_title": "Pretraga TV stanica",
        "search_placeholder": "Pretraga još nije implementirana (Faza 3).",
        "favourites_title": "Omiljene stanice",
        "favourites_placeholder": "Omiljene stanice stižu u Fazi 6.",
        "settings_title": "Podešavanja",
        "settings_placeholder": "Podešavanja stižu u Fazi 7.",
        "about_title": "O aplikaciji",
        "about_note": "Aplikacija prikazuje TV rasporede, ne TV prenos.",
    },
}


def t(key, language=DEFAULT_LANGUAGE):
    """Vraca tekst za kljuc. Nepostojeci kljuc se vidi kao [kljuc]."""
    table = STRINGS.get(language) or STRINGS[DEFAULT_LANGUAGE]
    return table.get(key, "[%s]" % key)
