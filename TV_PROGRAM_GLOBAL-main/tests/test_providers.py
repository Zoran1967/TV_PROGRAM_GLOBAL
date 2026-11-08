"""Testovi adaptera TvProfil i registra izvora (bez interneta, sa laznim preuzimanjem)."""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.models.schedule import ChannelSource  # noqa: E402
from app.providers import registry as registry_module  # noqa: E402
from app.providers.base import ProviderInfo  # noqa: E402
from app.providers.errors import (  # noqa: E402
    InvalidSourceError,
    NetworkError,
    ZoneUnavailableError,
)
from app.providers.registry import load_registry  # noqa: E402
from app.providers.tvprofil import TvProfilProvider  # noqa: E402

TEMPLATE = "https://example.invalid/xmltv/{id}/weekly_{id}.xml"
INFO = ProviderInfo("tvprofil", "TvProfil", "pending", "Izvor: test", "https://example.invalid", 3600)
XML = (
    '<?xml version="1.0"?><tv>'
    '<programme start="20261106193000" stop="20261106203000" channel="rts1.sr"><title>Test A</title></programme>'
    '<programme start="20261106203000" channel="rts1.sr"><title>Test B</title></programme>'
    "</tv>"
).encode()


def source(channel_id="rts1.sr", timezone="Europe/Belgrade"):
    return ChannelSource("tvprofil", channel_id, timezone, 7, 0)


def make(fetcher):
    return TvProfilProvider(INFO, TEMPLATE, timeout=7.0, fetcher=fetcher)


def test_url_and_timeout_are_passed_to_the_fetcher():
    calls = []

    def fetcher(url, timeout):
        calls.append((url, timeout))
        return XML

    programmes = make(fetcher).fetch_programmes(source())
    assert calls == [("https://example.invalid/xmltv/rts1.sr/weekly_rts1.sr.xml", 7.0)]
    assert [p.title for p in programmes] == ["Test A", "Test B"]
    # 19:30 po lokalnom vremenu u Beogradu (zimsko, +01:00) je 18:30 UTC
    assert programmes[0].start_utc == 1793989800


@pytest.mark.parametrize("bad_id", ["", None, "../etc/passwd", "a b", "RTS1.sr", "x" * 200,
                                    "rts1.sr?x=1", "rts1.sr/../../x", "-rts1", "rts1\n.sr", "а.sr"])
def test_invalid_channel_ids_never_reach_the_network(bad_id):
    def fetcher(url, timeout):
        raise AssertionError("ne sme da se poziva")

    with pytest.raises(InvalidSourceError):
        make(fetcher).fetch_programmes(source(bad_id))


def test_unknown_zone_is_reported_before_any_download():
    def fetcher(url, timeout):
        raise AssertionError("ne sme da se poziva")

    with pytest.raises(ZoneUnavailableError):
        make(fetcher).fetch_programmes(source(timezone="Nema/Zone"))


def test_missing_zone_with_floating_times_is_an_error():
    with pytest.raises(ZoneUnavailableError):
        make(lambda url, timeout: XML).fetch_programmes(source(timezone=None))


def test_network_errors_pass_through():
    def fetcher(url, timeout):
        raise NetworkError("nema veze")

    with pytest.raises(NetworkError):
        make(fetcher).fetch_programmes(source())


# ---- registar --------------------------------------------------------------

def write_config(tmp_path, providers):
    path = tmp_path / "providers.json"
    path.write_text(json.dumps({"providers": providers}), encoding="utf-8")
    return str(path)


def entry(**overrides):
    base = {"id": "tvprofil", "name": "TvProfil", "adapter": "tvprofil", "enabled": True,
            "license_status": "pending", "url_template": TEMPLATE,
            "attribution_text": "x", "attribution_url": "y", "min_refresh_seconds": 600}
    base.update(overrides)
    return base


def test_pending_license_works_only_in_dev_builds(tmp_path):
    path = write_config(tmp_path, [entry()])
    assert load_registry(path, flavor="dev").ids() == ["tvprofil"]
    assert load_registry(path, flavor="release").ids() == []


def test_approved_license_works_in_release(tmp_path):
    path = write_config(tmp_path, [entry(license_status="approved")])
    assert load_registry(path, flavor="release").ids() == ["tvprofil"]


@pytest.mark.parametrize("status", ["", "denied", "unknown", "APPROVED"])
def test_other_license_statuses_are_never_loaded(tmp_path, status):
    path = write_config(tmp_path, [entry(license_status=status)])
    assert load_registry(path, flavor="dev").ids() == []
    assert load_registry(path, flavor="release").ids() == []


def test_disabled_and_unknown_adapters_are_skipped(tmp_path):
    path = write_config(tmp_path, [entry(enabled=False), entry(id="x", adapter="nepoznat")])
    assert load_registry(path, flavor="dev").ids() == []


def test_registry_info_is_loaded(tmp_path):
    path = write_config(tmp_path, [entry(min_refresh_seconds=123)])
    provider = load_registry(path, flavor="dev").get("tvprofil")
    assert provider.info.min_refresh_seconds == 123
    assert provider.info.license_status == "pending"
    assert load_registry(path, flavor="dev").get("nema") is None


def test_broken_config_raises_instead_of_silently_working(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ ovo nije json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_registry(str(path))
    with pytest.raises(OSError):
        load_registry(str(tmp_path / "nema.json"))


def test_shipped_config_is_valid_and_pending():
    config_path = registry_module.DEFAULT_CONFIG_PATH
    with open(config_path, encoding="utf-8") as handle:
        providers = json.load(handle)["providers"]
    tvprofil = next(p for p in providers if p["id"] == "tvprofil")
    assert tvprofil["license_status"] == "pending"
    assert tvprofil["url_template"].startswith("https://")
    assert "{id}" in tvprofil["url_template"]
    assert "key" not in json.dumps(tvprofil).lower().replace("attribution", "")
    assert load_registry(config_path, flavor="release").ids() == []
