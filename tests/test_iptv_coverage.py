"""Test provere pokrivenosti iptv-org/epg (izmisljeni podaci, bez interneta)."""

import io
import os
import sqlite3
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, "tools")):
    if path not in sys.path:
        sys.path.insert(0, path)

import iptv_org_coverage as tool  # noqa: E402

CHANNELS_XML = (
    '<?xml version="1.0"?><channels>'
    '<channel site="sajt-a.hr" lang="hr" xmltv_id="HTV1.hr" site_id="1">HTV 1</channel>'
    '<channel site="sajt-a.hr" lang="hr" xmltv_id="RTS1.rs@SD" site_id="2">RTS 1</channel>'
    '<channel site="sajt-a.hr" lang="hr" site_id="3">bez oznake</channel>'
    "</channels>"
).encode()


def make_tarball(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_parse_channels_xml_strips_feed_and_skips_entries_without_id():
    assert tool.parse_channels_xml(CHANNELS_XML) == [("sajt-a.hr", "HTV1.hr"), ("sajt-a.hr", "RTS1.rs")]


def test_read_tarball_only_uses_sites_channels_files():
    data = make_tarball({
        "epg-master/sites/sajt-a.hr/sajt-a.hr_hr.channels.xml": CHANNELS_XML,
        "epg-master/sites/sajt-a.hr/sajt-a.hr.config.js": b"nije xml",
        "epg-master/other/x.channels.xml": CHANNELS_XML,
        "epg-master/sites/sajt-b.rs/pokvaren.channels.xml": b"<channels><channel",
    })
    assert tool.read_tarball(data) == {"sajt-a.hr": {"HTV1.hr", "RTS1.rs"}}


def test_coverage_and_report(tmp_path):
    database = tmp_path / "catalog.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE channel (id INTEGER PRIMARY KEY, catalog_id TEXT, name TEXT, country_code TEXT);"
        "CREATE TABLE channel_source (channel_id INTEGER, source_id TEXT);"
        "INSERT INTO channel VALUES (1,'HTV1.hr','HTV 1','HR'),(2,'City.ba','City TV','BA'),"
        "(3,'Bez.rs','Bez izvora','RS');"
        "INSERT INTO channel_source VALUES (1,'tvprofil'),(2,'tvprofil');"
    )
    connection.commit()
    connection.close()
    channels = tool.our_channels(str(database))
    assert [item[0] for item in channels] == ["City.ba", "HTV1.hr"]  # samo stanice sa izvorom
    per_site = {"sajt-a.hr": {"HTV1.hr", "RTS1.rs"}}
    found = tool.coverage(channels, per_site)
    assert found == {"City.ba": [], "HTV1.hr": ["sajt-a.hr"]}
    report = tool.render(channels, found, per_site)
    assert "Pokriveno bar jednim iptv-org sajtom: **1**" in report
    assert "City TV (BA) - City.ba" in report


def test_main_writes_report_from_a_local_archive(tmp_path):
    database = tmp_path / "catalog.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE channel (id INTEGER PRIMARY KEY, catalog_id TEXT, name TEXT, country_code TEXT);"
        "CREATE TABLE channel_source (channel_id INTEGER, source_id TEXT);"
        "INSERT INTO channel VALUES (1,'HTV1.hr','HTV 1','HR');"
        "INSERT INTO channel_source VALUES (1,'tvprofil');"
    )
    connection.commit()
    connection.close()
    archive = tmp_path / "epg.tar.gz"
    archive.write_bytes(make_tarball({"epg-master/sites/sajt-a.hr/a.channels.xml": CHANNELS_XML}))
    out = tmp_path / "izvestaj.md"
    assert tool.main(["--db", str(database), "--archive", str(archive), "--out", str(out)]) == 0
    assert "HTV 1 (HR) - HTV1.hr: sajt-a.hr" in out.read_text(encoding="utf-8")
