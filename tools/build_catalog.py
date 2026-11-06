"""Pravi data/catalog_seed.db iz baze iptv-org/database.

Podaci: https://github.com/iptv-org/database (Unlicense / CC0, javno vlasnistvo).
Ova skripta se pokrece van aplikacije i ne ulazi u APK.

Upotreba:
    python tools/build_catalog.py                 # preuzima podatke sa GitHub-a
    python tools/build_catalog.py --csv-dir PUTANJA   # koristi vec preuzete CSV fajlove

Izbacuju se ugasene stanice (kolona "closed") i stanice za odrasle (is_nsfw).
Logotipi se ne uzimaju, jer njihova prava nisu proverena.
"""

import argparse
import csv
import datetime
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.database.schema import create_schema  # noqa: E402
from app.utils.text import normalize_key, normalize_text  # noqa: E402

SOURCE_REPO = "https://github.com/iptv-org/database"
RAW_BASE = "https://raw.githubusercontent.com/iptv-org/database"
COMMIT_API = "https://api.github.com/repos/iptv-org/database/commits/master"
DEFAULT_OUT = os.path.join(ROOT, "data", "catalog_seed.db")
LICENSE_TEXT = "Unlicense / CC0 (iptv-org/database)"

# Izvor rasporeda TvProfil: stanice sa oznakom drzave u ID-ju (npr. "rts1.sr").
# Vremena u njihovim fajlovima su lokalno vreme drzave (vidi README), zato se
# vezuju samo stanice cija oznaka odredjuje jednu vremensku zonu.
TVPROFIL_SOURCE_ID = "tvprofil"
TVPROFIL_COUNTRIES = {
    "sr": ("RS", "Europe/Belgrade"),
    "hr": ("HR", "Europe/Zagreb"),
    "ba": ("BA", "Europe/Sarajevo"),
    "cg": ("ME", "Europe/Podgorica"),
    "mk": ("MK", "Europe/Skopje"),
    "si": ("SI", "Europe/Ljubljana"),
}
DEFAULT_TVPROFIL_CSV = os.path.join(ROOT, "data", "sources", "tvprofil_channels.csv")
DEFAULT_REPORT = os.path.join(ROOT, "data", "sources", "tvprofil_mapping_report.csv")
DEFAULT_OVERRIDES = os.path.join(ROOT, "data", "sources", "tvprofil_overrides.csv")


def map_tvprofil(connection, rows, overrides=None):
    """Povezuje TvProfil kanale sa stanicama iz kataloga.

    Povezuje samo kada je podudaranje jednoznacno: ista drzava i isti normalizovani
    naziv (ili ID bez oznake drzave), tacno jedna stanica u katalogu, i tacno jedan
    TvProfil kanal za tu stanicu. Sve ostalo ostaje nepovezano i ide u izvestaj.
    `overrides` ({xmltv_id: catalog_id}) su rucno potvrdjene veze za stanice cije se
    ime razlikuje (npr. HTV1 = HRT 1); prazan catalog_id znaci "ne povezuj".
    Vraca (statistika, izvestaj).
    """
    overrides = overrides or {}
    index = {}
    for country, key, channel_id in connection.execute(
        "SELECT c.country_code, a.alias_key, a.channel_id FROM channel_alias a"
        " JOIN channel c ON c.id = a.channel_id WHERE a.word_offset = 0"
    ):
        index.setdefault((country, key), set()).add(channel_id)
    catalog_ids = dict(connection.execute("SELECT id, catalog_id FROM channel"))
    channel_by_catalog_id = {value: key for key, value in catalog_ids.items()}

    report = []
    claims = {}
    for row in rows:
        xmltv_id = row["xmltv_id"].strip()
        name = row["name"].strip()
        days = int(row["days_available"])
        suffix = xmltv_id.rsplit(".", 1)[-1]
        entry = {"xmltv_id": xmltv_id, "name": name, "days": days,
                 "status": "", "catalog_id": "", "channel_id": None}
        report.append(entry)
        if suffix not in TVPROFIL_COUNTRIES:
            entry["status"] = "nepodrzana_oznaka"
            continue
        if days <= 0:
            entry["status"] = "izvor_nema_podataka"
            continue
        country = TVPROFIL_COUNTRIES[suffix][0]
        if xmltv_id in overrides and not overrides[xmltv_id]:
            entry["status"] = "rucno_iskljuceno"
            continue
        if xmltv_id in overrides:
            channel_id = channel_by_catalog_id.get(overrides[xmltv_id])
            if channel_id is None:
                entry["status"] = "override_nepoznat_kanal"
                continue
            entry["channel_id"] = channel_id
            claims.setdefault(channel_id, []).append(entry)
            continue
        keys = {normalize_key(name), normalize_key(xmltv_id.rsplit(".", 1)[0])}
        keys.discard("")
        candidates = set()
        for key in keys:
            candidates |= index.get((country, key), set())
        if not candidates:
            entry["status"] = "bez_poklapanja"
        elif len(candidates) > 1:
            entry["status"] = "vise_poklapanja"
        else:
            entry["channel_id"] = next(iter(candidates))
            claims.setdefault(entry["channel_id"], []).append(entry)

    for channel_id, entries in claims.items():
        if len(entries) > 1:
            for entry in entries:
                entry["status"] = "sukob_vise_kanala"
                entry["channel_id"] = None
            continue
        entry = entries[0]
        suffix = entry["xmltv_id"].rsplit(".", 1)[-1]
        connection.execute(
            "INSERT INTO channel_source (channel_id, source_id, source_channel_id,"
            " timezone, days_available, priority) VALUES (?, ?, ?, ?, ?, 0)",
            (channel_id, TVPROFIL_SOURCE_ID, entry["xmltv_id"],
             TVPROFIL_COUNTRIES[suffix][1], entry["days"]),
        )
        entry["status"] = "povezano"
        entry["catalog_id"] = catalog_ids[channel_id]

    stats = {"tvprofil_u_spisku": len(report)}
    for entry in report:
        key = "tvprofil_" + entry["status"]
        stats[key] = stats.get(key, 0) + 1
    return stats, report


def write_report(path, report):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["xmltv_id", "name", "days_available", "status", "catalog_id"])
        for entry in sorted(report, key=lambda item: (item["status"], item["xmltv_id"])):
            writer.writerow([entry["xmltv_id"], entry["name"], entry["days"],
                             entry["status"], entry["catalog_id"]])


def read_csv_text(text):
    return list(csv.DictReader(io.StringIO(text, newline="")))


def split_alt_names(value):
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def build_catalog(channel_rows, country_rows, out_path, meta=None, tvprofil_rows=None,
                  tvprofil_overrides=None):
    """Pravi bazu kataloga. Vraca recnik sa brojevima (statistika)."""
    if os.path.exists(out_path):
        os.remove(out_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    countries = {row["code"].strip(): row["name"].strip() for row in country_rows}
    stats = {
        "ukupno_u_izvoru": len(channel_rows),
        "preskoceno_ugaseno": 0,
        "preskoceno_nsfw": 0,
        "preskoceno_nepoznata_zemlja": 0,
        "preskoceno_bez_kljuca": 0,
        "kanala": 0,
        "naziva": 0,
        "redova_indeksa": 0,
    }

    connection = sqlite3.connect(out_path)
    try:
        create_schema(connection)
        used_countries = set()
        for row in sorted(channel_rows, key=lambda item: item["id"]):
            if (row.get("closed") or "").strip():
                stats["preskoceno_ugaseno"] += 1
                continue
            if (row.get("is_nsfw") or "").strip().lower() == "true":
                stats["preskoceno_nsfw"] += 1
                continue
            country_code = (row.get("country") or "").strip()
            if country_code not in countries:
                stats["preskoceno_nepoznata_zemlja"] += 1
                continue

            name = (row.get("name") or "").strip()
            aliases = [(name, "name")] + [
                (alt, "alt") for alt in split_alt_names(row.get("alt_names"))
            ]
            keyed = []
            seen = set()
            for alias, kind in aliases:
                words = normalize_text(alias).split()
                for offset in range(len(words)):
                    key = "".join(words[offset:])
                    if key not in seen:
                        seen.add(key)
                        keyed.append((alias, key, kind, offset))
            if not keyed:
                stats["preskoceno_bez_kljuca"] += 1
                continue
            alias_count = len({alias for alias, _key, _kind, _offset in keyed})

            network = (row.get("network") or "").strip() or None
            cursor = connection.execute(
                "INSERT INTO channel (catalog_id, name, name_key, country_code, network)"
                " VALUES (?, ?, ?, ?, ?)",
                (row["id"].strip(), name, normalize_key(name), country_code, network),
            )
            channel_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO channel_alias (channel_id, alias, alias_key, kind, word_offset)"
                " VALUES (?, ?, ?, ?, ?)",
                [(channel_id, alias, key, kind, offset) for alias, key, kind, offset in keyed],
            )
            used_countries.add(country_code)
            stats["kanala"] += 1
            stats["naziva"] += alias_count
            stats["redova_indeksa"] += len(keyed)

        connection.executemany(
            "INSERT INTO country (code, name) VALUES (?, ?)",
            sorted((code, countries[code]) for code in used_countries),
        )
        if tvprofil_rows:
            mapping_stats, report = map_tvprofil(
                connection, tvprofil_rows, tvprofil_overrides
            )
            stats.update(mapping_stats)
            stats["_tvprofil_report"] = report
        meta = dict(meta or {})
        meta.update(
            {
                "license": LICENSE_TEXT,
                "channels": str(stats["kanala"]),
                "aliases": str(stats["naziva"]),
                "index_rows": str(stats["redova_indeksa"]),
                "countries": str(len(used_countries)),
                "tvprofil_linked": str(stats.get("tvprofil_povezano", 0)),
            }
        )
        connection.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)", sorted(meta.items())
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()
    return stats


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "tv-program-global"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8-sig")


def source_commit():
    """Vraca SHA poslednjeg commit-a izvora ili None."""
    try:
        return json.loads(download(COMMIT_API))["sha"]
    except Exception:
        pass
    try:
        output = subprocess.run(
            ["git", "ls-remote", SOURCE_REPO, "HEAD"],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
        match = re.match(r"([0-9a-f]{40})\s", output)
        return match.group(1) if match else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--csv-dir", help="folder sa channels.csv i countries.csv")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--commit", help="commit izvora (upisuje se u meta tabelu)")
    parser.add_argument("--built-at", help="vreme izrade (podrazumevano: sada, UTC)")
    parser.add_argument("--tvprofil-csv", default=DEFAULT_TVPROFIL_CSV,
                        help="spisak TvProfil kanala (data/sources/tvprofil_channels.csv)")
    parser.add_argument("--tvprofil-overrides", default=DEFAULT_OVERRIDES,
                        help="rucno potvrdjene veze (xmltv_id,catalog_id,note)")
    parser.add_argument("--report", default=DEFAULT_REPORT,
                        help="izvestaj o povezivanju sa TvProfil kanalima")
    args = parser.parse_args()

    if args.csv_dir:
        with open(os.path.join(args.csv_dir, "channels.csv"), encoding="utf-8-sig") as handle:
            channels_text = handle.read()
        with open(os.path.join(args.csv_dir, "countries.csv"), encoding="utf-8-sig") as handle:
            countries_text = handle.read()
        commit = args.commit or "nepoznat"
    else:
        # Podaci se preuzimaju za tacno odredjeni commit, da se zna odakle dolaze
        commit = args.commit or source_commit()
        base = "%s/%s/data" % (RAW_BASE, commit or "master")
        channels_text = download(base + "/channels.csv")
        countries_text = download(base + "/countries.csv")
        commit = commit or "nepoznat"

    built_at = args.built_at or datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    tvprofil_rows = None
    if args.tvprofil_csv and os.path.isfile(args.tvprofil_csv):
        with open(args.tvprofil_csv, encoding="utf-8-sig", newline="") as handle:
            tvprofil_rows = list(csv.DictReader(handle))
    overrides = {}
    if args.tvprofil_overrides and os.path.isfile(args.tvprofil_overrides):
        with open(args.tvprofil_overrides, encoding="utf-8-sig", newline="") as handle:
            overrides = {row["xmltv_id"].strip(): row["catalog_id"].strip()
                         for row in csv.DictReader(handle)}
    stats = build_catalog(
        read_csv_text(channels_text),
        read_csv_text(countries_text),
        args.out,
        meta={"source_url": SOURCE_REPO, "source_commit": commit, "built_at": built_at},
        tvprofil_rows=tvprofil_rows,
        tvprofil_overrides=overrides,
    )
    report = stats.pop("_tvprofil_report", None)
    if report is not None:
        write_report(args.report, report)
    for name, value in stats.items():
        print("%-34s %s" % (name, value))
    print("Baza: %s (%.1f MB)" % (args.out, os.path.getsize(args.out) / 1e6))


if __name__ == "__main__":
    main()
