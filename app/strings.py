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
        "schedule_back": "Nazad na rezultate",
        "schedule_loading": "Učitavam raspored...",
        "schedule_title": "Raspored: {name} ({country})",
        "schedule_no_source": "Za ovu stanicu nema povezanog izvora rasporeda.",
        "schedule_unavailable": "Izvor rasporeda za ovu stanicu nije dostupan u ovoj verziji aplikacije.",
        "schedule_date_zone": "Datum: {date} · Zona: {zone} ({label})",
        "schedule_source": "Izvor: {source} · osveženo {time}",
        "schedule_stale": "Prikazani su stariji podaci. Osvežavanje nije uspelo: {reason}",
        "schedule_dev_note": "Probna verzija: licenca izvora nije potvrđena.",
        "schedule_net_error": "Raspored nije preuzet: nema veze ili je izvor nedostupan.",
        "schedule_http_error": "Izvor je vratio grešku ({code}).",
        "schedule_http_404": "Izvor nema raspored za ovu stanicu (greška 404).",
        "schedule_rate_limited": "Izvor traži pauzu. Pokušajte ponovo kasnije.",
        "schedule_empty": "Izvor trenutno nema emisije za ovu stanicu.",
        "schedule_parse_error": "Podaci izvora nisu ispravni.",
        "schedule_zone_error": "Vremenska zona stanice nije poznata. Raspored se ne prikazuje.",
        "schedule_no_data_date": "Izvor nema program za današnji datum ({date}).",
        "schedule_error": "Došlo je do neočekivane greške pri učitavanju rasporeda.",
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
