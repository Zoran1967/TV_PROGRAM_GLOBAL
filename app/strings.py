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
        "search_hint": "Naziv ili skraćenica stanice",
        "search_examples": "Primeri: RTS1, BBC One, CNN, HRT1",
        "search_too_short": "Unesite bar 2 slova ili cifre.",
        "search_not_found": "Stanica nije pronađena.",
        "search_error": "Katalog stanica nije dostupan. Pretraga trenutno ne radi.",
        "search_count": "Pronađeno stanica: {count}",
        "search_truncated": "Prikazano je prvih {count} rezultata. Dopunite unos da suzite izbor.",
        "result_found_as": "pronađeno kao: {alias}",
        "result_id": "ID: {id}",
        "selected_label": "Izabrano: {name} ({country})",
        "selected_note": "Prikaz rasporeda stiže u narednim fazama.",
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
