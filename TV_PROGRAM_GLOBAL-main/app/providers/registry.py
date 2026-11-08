"""Registar izvora rasporeda: cita data/providers.json i pravi adaptere."""

import json
import logging
import os

from app.build_flavor import FLAVOR
from app.providers import tvprofil
from app.providers.base import ProviderInfo

LOGGER = logging.getLogger(__name__)

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(_APP_ROOT), "data", "providers.json")

# Ime adaptera iz providers.json -> funkcija koja pravi adapter.
# Novi izvor = novi modul u app/providers + unos ovde + unos u providers.json.
ADAPTER_FACTORIES = {"tvprofil": tvprofil.create_provider}

LICENSE_APPROVED = "approved"
LICENSE_PENDING = "pending"


class ProviderRegistry:
    def __init__(self, providers=None):
        self._providers = dict(providers or {})

    def get(self, source_id):
        return self._providers.get(source_id)

    def ids(self):
        return sorted(self._providers)


def _allowed(license_status, flavor):
    if license_status == LICENSE_APPROVED:
        return True
    return license_status == LICENSE_PENDING and flavor == "dev"


def load_registry(config_path=DEFAULT_CONFIG_PATH, flavor=FLAVOR, factories=None):
    """Pravi registar. Izvor koji nije dozvoljen za ovu vrstu izgradnje se preskace."""
    factories = factories or ADAPTER_FACTORIES
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    providers = {}
    for entry in config.get("providers", []):
        source_id = entry.get("id")
        if not entry.get("enabled", True):
            continue
        status = entry.get("license_status", "")
        if not _allowed(status, flavor):
            LOGGER.warning("Izvor %s preskocen: licenca %r nije dozvoljena u izgradnji %r",
                           source_id, status, flavor)
            continue
        factory = factories.get(entry.get("adapter"))
        if factory is None:
            LOGGER.warning("Izvor %s preskocen: nepoznat adapter %r", source_id, entry.get("adapter"))
            continue
        info = ProviderInfo(
            id=source_id,
            name=entry["name"],
            license_status=status,
            attribution_text=entry.get("attribution_text", ""),
            attribution_url=entry.get("attribution_url", ""),
            min_refresh_seconds=int(entry.get("min_refresh_seconds", 3600)),
        )
        providers[source_id] = factory(entry, info)
    return ProviderRegistry(providers)
