"""Adapter za TvProfil XMLTV servis (https://tvprofil.net/xmltv/).

Svaka stanica ima svoj fajl sa rasporedom za nekoliko dana. Vremena u fajlu
su lokalno vreme drzave stanice (bez pomaka), zato adapter koristi zonu iz
tabele channel_source.
"""

import logging
import re
from datetime import datetime, timedelta

from app.models.schedule import ChannelSource
from app.net.http_client import fetch_bytes
from app.providers.base import ProviderInfo, ScheduleProvider
from app.providers.errors import EmptyScheduleError, HttpStatusError, InvalidSourceError
from app.providers.xmltv import load_zone, parse_xmltv

LOGGER = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,80}$")

# Dnevni fajlovi TvProfila pokrivaju dan od 00 do 24 casa po srednjeevropskom vremenu (CET)
DAILY_ZONE = "Europe/Belgrade"
DAILY_DAYS = 2  # danas i sutra, koliko ima i nedeljni fajl


class TvProfilProvider(ScheduleProvider):
    def __init__(self, info, url_template, timeout=20.0, fetcher=fetch_bytes,
                 daily_url_template=None, now=None):
        self.info = info
        self._url_template = url_template
        self._daily_url_template = daily_url_template  # rezerva kad nedeljni fajl vrati 404
        self._timeout = timeout
        self._fetcher = fetcher
        self._now = now  # za testove: funkcija koja vraca trenutno vreme (sa zonom)

    def build_url(self, source_channel_id):
        if not _ID_RE.match(source_channel_id or ""):
            raise InvalidSourceError("Neispravna oznaka stanice: %r" % source_channel_id)
        return self._url_template.format(id=source_channel_id)

    def fetch_programmes(self, source: ChannelSource):
        url = self.build_url(source.source_channel_id)
        zone = load_zone(source.timezone) if source.timezone else None
        try:
            data = self._fetcher(url, timeout=self._timeout)
        except HttpStatusError as error:
            if error.status != 404 or not self._daily_url_template:
                raise
            # Nedeljnog fajla nema; dnevni fajlovi mogu da postoje
            return self._fetch_daily(source, zone, error)
        result = parse_xmltv(data, source.source_channel_id, zone)
        LOGGER.info(
            "TvProfil %s: %d emisija (ukupno u fajlu %d, preskoceno: lose vreme %d, bez naslova %d)",
            source.source_channel_id, result.stats.kept, result.stats.total,
            result.stats.bad_time, result.stats.no_title,
        )
        return result.programmes

    def _daily_dates(self):
        zone = load_zone(DAILY_ZONE)
        now = self._now() if self._now else datetime.now(zone)
        today = now.astimezone(zone).date()
        return [(today + timedelta(days=offset)).isoformat() for offset in range(DAILY_DAYS)]

    def _fetch_daily(self, source, zone, weekly_error):
        """Sklapa raspored iz dnevnih fajlova; ako nijedan ne postoji, vraca originalnu gresku."""
        programmes = []
        for date in self._daily_dates():
            url = self._daily_url_template.format(id=source.source_channel_id, date=date)
            try:
                data = self._fetcher(url, timeout=self._timeout)
                parsed = parse_xmltv(data, source.source_channel_id, zone)
            except HttpStatusError as error:
                if error.status == 404:
                    continue  # taj dan ne postoji
                raise
            except EmptyScheduleError:
                continue  # fajl postoji, ali bez emisija za taj dan
            programmes.extend(parsed.programmes)
        if not programmes:
            raise weekly_error
        unique = {(item.start_utc, item.title): item for item in programmes}
        LOGGER.info("TvProfil %s: nedeljni fajl nedostaje, %d emisija iz dnevnih fajlova",
                    source.source_channel_id, len(unique))
        return sorted(unique.values(), key=lambda item: item.start_utc)


def create_provider(config, info, fetcher=fetch_bytes):
    return TvProfilProvider(
        info,
        url_template=config["url_template"],
        timeout=float(config.get("timeout_seconds", 20)),
        fetcher=fetcher,
        daily_url_template=config.get("daily_url_template"),
    )
