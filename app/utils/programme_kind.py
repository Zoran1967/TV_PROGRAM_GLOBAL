"""Odredjivanje vrste emisije (film, serija, ostalo) samo iz podataka koje izvor daje.

Nista se ne nagadja po naslovu: serija je emisija sa brojem sezone/epizode ili sa kategorijom
koja to kaze, film je emisija sa kategorijom koja to kaze. Sve ostalo je \"ostalo\".
"""

KIND_FILM = "film"
KIND_SERIES = "series"
KIND_OTHER = "other"

# Reci (u malim slovima, bez kvacica) koje u kategoriji znace seriju
_SERIES_WORDS = (
    "serij", "serial", "series", "sitcom", "telenovel", "sapunic", "soap",
    "teleroman", "dizi",
)
# Reci koje u kategoriji znace film
_FILM_WORDS = ("film", "movie", "bioskop", "cinema", "kino")
# Dokumentarni i slicni \"filmovi\" nisu igrani film
_NOT_FILM_WORDS = ("dokument", "documentar")

_TRANSLATION = str.maketrans({
    "č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "d",
    "Č": "c", "Ć": "c", "Š": "s", "Ž": "z", "Đ": "d",
})


def _plain(text):
    return text.translate(_TRANSLATION).casefold()


def programme_kind(programme):
    """KIND_SERIES, KIND_FILM ili KIND_OTHER za Programme (ili bilo sta sa tim poljima)."""
    if programme is None:
        return KIND_OTHER
    if programme.season is not None or programme.episode is not None:
        return KIND_SERIES
    names = [name for name in (programme.genres or ()) if name]
    if programme.category and programme.category not in names:
        names.append(programme.category)
    plain = [_plain(name) for name in names]
    if any(word in name for name in plain for word in _SERIES_WORDS):
        return KIND_SERIES
    if any(word in name for name in plain for word in _NOT_FILM_WORDS):
        return KIND_OTHER
    if any(word in name for name in plain for word in _FILM_WORDS):
        return KIND_FILM
    return KIND_OTHER
