"""Proverava koje stanice iz kataloga aplikacije (one sa izvorom rasporeda) iptv-org/epg pokriva.

iptv-org/epg ima po sajtu spisak stanica (sites/<sajt>/*.channels.xml) sa oznakom xmltv_id, a to je
ista oznaka kao catalog_id u data/catalog_seed.db. Skripta preuzima taj repozitorijum, uporedi oznake
i upise izvestaj (Markdown). Ne menja aplikaciju i ne preuzima nikakve rasporede.

Pokretanje (potreban je internet):  python tools/iptv_org_coverage.py
Samo standardna biblioteka.
"""

import argparse
import collections
import io
import os
import sqlite3
import sys
import tarfile
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "catalog_seed.db")
DEFAULT_OUT = os.path.join(ROOT, "docs", "pokrivenost_iptv-org.md")
TARBALL_URL = "https://codeload.github.com/iptv-org/epg/tar.gz/refs/heads/master"
MAX_TARBALL_BYTES = 200 * 1024 * 1024


def our_channels(db_path=DB_PATH):
    """[(catalog_id, naziv, drzava)] za stanice koje aplikacija ume da cita (imaju izvor rasporeda)."""
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT DISTINCT c.catalog_id, c.name, c.country_code FROM channel c "
            "JOIN channel_source s ON s.channel_id = c.id ORDER BY c.country_code, c.name"
        ).fetchall()
    finally:
        connection.close()
    return [tuple(row) for row in rows]


def normalize_id(xmltv_id):
    """RTS1.rs@SD -> RTS1.rs (iptv-org dodaje @feed za varijante istog kanala)."""
    return (xmltv_id or "").split("@", 1)[0].strip()


def parse_channels_xml(data):
    """[(sajt, xmltv_id)] iz jednog *.channels.xml fajla."""
    root = ET.fromstring(data)
    found = []
    for node in root.iter("channel"):
        xmltv_id = normalize_id(node.get("xmltv_id"))
        site = (node.get("site") or "").strip()
        if xmltv_id and site:
            found.append((site, xmltv_id))
    return found


def read_tarball(data):
    """{sajt: set(xmltv_id)} iz tar.gz arhive iptv-org/epg (samo sites/*/*.channels.xml)."""
    per_site = collections.defaultdict(set)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            parts = member.name.split("/")
            if not member.isfile() or not member.name.endswith(".channels.xml"):
                continue
            if "sites" not in parts:
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            try:
                for site, xmltv_id in parse_channels_xml(handle.read()):
                    per_site[site].add(xmltv_id)
            except ET.ParseError:
                continue  # pokvaren fajl se preskace
    return dict(per_site)


def coverage(channels, per_site):
    """{catalog_id: [sajtovi koji imaju stanicu]}."""
    by_id = collections.defaultdict(list)
    for site, ids in per_site.items():
        for xmltv_id in ids:
            by_id[xmltv_id].append(site)
    return {catalog_id: sorted(by_id.get(catalog_id, [])) for catalog_id, _name, _country in channels}


def render(channels, found, per_site):
    covered = [item for item in channels if found[item[0]]]
    missing = [item for item in channels if not found[item[0]]]
    lines = [
        "# Pokrivenost stanica rasporedima iz iptv-org/epg",
        "",
        "Stanice iz kataloga aplikacije koje imaju izvor rasporeda: **%d**." % len(channels),
        "Pokriveno bar jednim iptv-org sajtom: **%d**. Nije pokriveno nijednim: **%d**."
        % (len(covered), len(missing)),
        "",
        "Napomena: ovo samo kaze da stanica postoji u spisku sajta. Ne garantuje da sajt trenutno",
        "vraca raspored, niti da je dozvoljeno koristiti ga (proveriti uslove svakog sajta).",
        "",
        "## Po drzavama",
        "",
        "| Drzava | Stanica | Pokriveno | Nije pokriveno |",
        "| --- | --- | --- | --- |",
    ]
    totals = collections.OrderedDict()
    for catalog_id, _name, country in channels:
        row = totals.setdefault(country, [0, 0])
        row[0] += 1
        row[1] += 1 if found[catalog_id] else 0
    for country, (total, ok) in totals.items():
        lines.append("| %s | %d | %d | %d |" % (country, total, ok, total - ok))

    sites = collections.Counter(site for item in covered for site in found[item[0]])
    lines += ["", "## Koji sajtovi pokrivaju najvise nasih stanica", "",
              "| Sajt | Nasih stanica | Svih stanica u spisku sajta |", "| --- | --- | --- |"]
    for site, count in sites.most_common(15):
        lines.append("| %s | %d | %d |" % (site, count, len(per_site.get(site, ()))))

    lines += ["", "## Nije pokriveno nijednim sajtom (%d)" % len(missing), ""]
    lines += ["- %s (%s) - %s" % (name, country, catalog_id) for catalog_id, name, country in missing]
    lines += ["", "## Pokriveno (%d)" % len(covered), ""]
    for catalog_id, name, country in covered:
        lines.append("- %s (%s) - %s: %s" % (name, country, catalog_id, ", ".join(found[catalog_id])))
    return "\n".join(lines) + "\n"


def download(url=TARBALL_URL, timeout=180):
    request = urllib.request.Request(url, headers={"User-Agent": "TV_PROGRAM_GLOBAL coverage check"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(MAX_TARBALL_BYTES + 1)
    if len(data) > MAX_TARBALL_BYTES:
        raise RuntimeError("Arhiva je veca od dozvoljenog")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--archive", help="lokalna tar.gz arhiva umesto preuzimanja (za probu)")
    args = parser.parse_args(argv)

    channels = our_channels(args.db)
    if args.archive:
        with open(args.archive, "rb") as handle:
            data = handle.read()
    else:
        data = download()
    per_site = read_tarball(data)
    if not per_site:
        print("Nije nadjen nijedan spisak stanica u arhivi; izvestaj nije upisan.", file=sys.stderr)
        return 1
    report = render(channels, coverage(channels, per_site), per_site)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(report)
    print("Izvestaj upisan: %s (sajtova u spisku: %d)" % (args.out, len(per_site)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
