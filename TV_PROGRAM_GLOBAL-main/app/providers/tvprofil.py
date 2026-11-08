"""Adapter za TvProfil XMLTV servis (https://tvprofil.net/xmltv/).

Svaka stanica ima svoj fajl sa rasporedom za nekoliko dana. Vremena u fajlu
su lokalno vreme drzave stanice (bez pomaka), zato adapter koristi zonu iz
tabele channel_source.
"""

import logging
import re

from app.models.schedule import ChannelSource
from app.net.http_client import fetch_bytes
from app.providers.base import ProviderInfo, ScheduleProvider
from app.providers.errors import InvalidSourceError
from app.providers.xmltv import load_zone, parse_xmltv

LOGGER = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,80}$")


class TvProfilProvider(ScheduleProvider):
    def __init__(self, info, url_template, timeout=20.0, fetcher=fetch_bytes):
        self.info = info
        self._url_template = url_template
        self._timeout = timeout
        self._fetcher = fetcher

    def build_url(self, source_channel_id):
        if not _ID_RE.match(source_channel_id or ""):
            raise InvalidSourceError("Neispravna oznaka stanice: %r" % source_channel_id)
        return self._url_template.format(id=source_channel_id)

    def fetch_programmes(self, source: ChannelSource):
        url = self.build_url(source.source_channel_id)
        zone = load_zone(source.timezone) if source.timezone else None
        data = self._fetcher(url, timeout=self._timeout)
        result = parse_xmltv(data, source.source_channel_id, zone)
        LOGGER.info(
            "TvProfil %s: %d emisija (ukupno u fajlu %d, preskoceno: lose vreme %d, bez naslova %d)",
            source.source_channel_id, result.stats.kept, result.stats.total,
            result.stats.bad_time, result.stats.no_title,
        )
        return result.programmes


def create_provider(config, info, fetcher=fetch_bytes):
    return TvProfilProvider(
        info,
        url_template=config["url_template"],
        timeout=float(config.get("timeout_seconds", 20)),
        fetcher=fetcher,
    )
