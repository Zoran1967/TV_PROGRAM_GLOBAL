"""Normalizacija teksta za pretragu stanica.

Kljuc za pretragu je tekst bez velikih slova, razmaka, interpunkcije i
dijakritika. Reci su isti tekst sa razmacima izmedju reci. Srpska cirilica se pretvara u latinicu, pa se "РТС 1", "RTS 1" i
"rts1" svode na isti kljuc "rts1".
"""

import unicodedata

MAX_QUERY_LENGTH = 64

_CYRILLIC_TO_ASCII = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "dj",
    "е": "e", "ж": "z", "з": "z", "и": "i", "ј": "j", "к": "k",
    "л": "l", "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "c", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "c", "џ": "dz", "ш": "s",
}

# Slova koja Unicode normalizacija ne razlaze na osnovno slovo i dijakritik
_SPECIAL_LETTERS = {
    "đ": "dj", "ł": "l", "ø": "o", "ð": "d",
    "æ": "ae", "œ": "oe", "ı": "i", "þ": "th",
}

_TRANSLATION = str.maketrans({**_CYRILLIC_TO_ASCII, **_SPECIAL_LETTERS})


def normalize_text(text):
    """Vraca normalizovane reci razdvojene jednim razmakom.

    Mala slova, bez dijakritika, cirilica pretvorena u latinicu; sve sto nije
    slovo ili cifra postaje razmak.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).casefold().translate(_TRANSLATION)
    text = unicodedata.normalize("NFKD", text)
    cleaned = "".join(
        char if char.isalnum() and not unicodedata.combining(char) else " "
        for char in text
        if not unicodedata.combining(char)
    )
    return " ".join(cleaned.split())


def normalize_key(text):
    """Vraca kljuc za pretragu (reci spojene bez razmaka); prazan ako nema slova ni cifara."""
    return normalize_text(text).replace(" ", "")


def clean_query(text):
    """Skracuje korisnicki unos na dozvoljenu duzinu."""
    return (text or "").strip()[:MAX_QUERY_LENGTH]
