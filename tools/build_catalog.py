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


def read_csv_text(text):
    return list(csv.DictReader(io.StringIO(text, newline="")))


def split_alt_names(value):
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def build_catalog(channel_rows, country_rows, out_path, meta=None):
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
        meta = dict(meta or {})
        meta.update(
            {
                "license": LICENSE_TEXT,
                "channels": str(stats["kanala"]),
                "aliases": str(stats["naziva"]),
                "index_rows": str(stats["redova_indeksa"]),
                "countries": str(len(used_countries)),
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
    stats = build_catalog(
        read_csv_text(channels_text),
        read_csv_text(countries_text),
        args.out,
        meta={"source_url": SOURCE_REPO, "source_commit": commit, "built_at": built_at},
    )
    for name, value in stats.items():
        print("%-30s %s" % (name, value))
    print("Baza: %s (%.1f MB)" % (args.out, os.path.getsize(args.out) / 1e6))


if __name__ == "__main__":
    main()
