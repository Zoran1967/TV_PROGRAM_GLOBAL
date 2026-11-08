"""Prikaz sata i datuma prema podesavanjima (24 h / 12 h, zona stanice / zona uredjaja).

Bez Kivy-ja, pa se lako testira. Vremena u rasporedu su vec "svesna zone" (aware),
ovde se samo biraju zona i oblik prikaza.
"""

import datetime


class ClockFormat:
    """hour12: 12-casovni prikaz; zone: ZoneInfo u koju se prevode vremena (None = ostaju
    u zoni stanice)."""

    def __init__(self, hour12=False, zone=None):
        self.hour12 = bool(hour12)
        self.zone = zone

    @property
    def converts(self):
        return self.zone is not None

    def convert(self, value):
        if value is None or self.zone is None:
            return value
        return value.astimezone(self.zone)

    def clock(self, value):
        """"19:30" ili "7:30 PM"."""
        value = self.convert(value)
        if not self.hour12:
            return "%02d:%02d" % (value.hour, value.minute)
        hour = value.hour % 12 or 12
        return "%d:%02d %s" % (hour, value.minute, "AM" if value.hour < 12 else "PM")

    def zone_label(self, value):
        """Skracenica zone (npr. "CET"); prazno ako je nema."""
        return self.convert(value).tzname() or ""

    def date_of(self, value):
        return self.convert(value).date()


def format_date(value, language):
    """Datum za prikaz: srpski "08.11.2026.", ostali jezici ISO "2026-11-08"."""
    if value is None:
        return ""
    if language == "sr":
        return "%02d.%02d.%d." % (value.day, value.month, value.year)
    return value.isoformat()


def format_epoch_clock(timestamp, zone, fmt):
    """Vreme iz Unix sekundi u zoni stanice (pa u zoni prikaza, ako je zadata)."""
    return fmt.clock(datetime.datetime.fromtimestamp(timestamp, zone))
