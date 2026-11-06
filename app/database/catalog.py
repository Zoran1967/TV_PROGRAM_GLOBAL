"""Pristup lokalnom katalogu stanica (samo citanje)."""

import os
import sqlite3
from pathlib import Path
from typing import NamedTuple

from app.database.schema import SCHEMA_VERSION
from app.models.channel import Channel

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CATALOG_PATH = os.path.join(os.path.dirname(_APP_ROOT), "data", "catalog_seed.db")

# Najveci mogucy Unicode znak; sluzi za gornju granicu opsega "pocinje sa".
_MAX_CHAR = "\U0010ffff"

_SELECT = """
SELECT c.id, c.catalog_id, c.name, c.country_code, co.name, c.network,
       a.alias, MIN({score}) AS score
FROM channel_alias a
JOIN channel c ON c.id = a.channel_id
JOIN country co ON co.code = c.country_code
WHERE {condition}
GROUP BY c.id
ORDER BY score, c.name_key, co.name, c.catalog_id
LIMIT :limit
"""

# Glavna pretraga (koristi indeks): kljuc je pocetak celog naziva ili pocetak
# neke njegove reci. Najpre naziv koji pocinje kljucem (tacno podudaranje je
# najkrace), zatim podudaranje od druge reci nadalje, pa kraci nazivi.
# Naziv ima prednost nad alternativnim nazivom.
_MAIN_SQL = _SELECT.format(
    score=(
        "(a.word_offset > 0) * 100000"
        " + length(a.alias_key) * 2 + (a.kind <> 'name')"
    ),
    condition="a.alias_key >= :key AND a.alias_key < :upper",
)

# Rezerva, samo kada glavna pretraga nema nijedan rezultat: kljuc se nalazi
# bilo gde u celom nazivu (npr. kucano iz sredine reci).
_CONTAINS_SQL = _SELECT.format(
    score="instr(a.alias_key, :key) * 1000 + length(a.alias_key) * 2 + (a.kind <> 'name')",
    condition="a.word_offset = 0 AND instr(a.alias_key, :key) > 1",
)


class CatalogError(Exception):
    """Katalog ne postoji, ne moze da se otvori ili ima pogresnu verziju."""


class CatalogMatches(NamedTuple):
    items: list  # [(Channel, naziv po kome je pronadjena)]
    truncated: bool


class CatalogDatabase:
    def __init__(self, path=DEFAULT_CATALOG_PATH):
        if not os.path.isfile(path):
            raise CatalogError("Katalog stanica ne postoji: %s" % path)
        try:
            uri = Path(path).resolve().as_uri() + "?mode=ro"
            self._connection = sqlite3.connect(uri, uri=True)
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.Error as error:
            raise CatalogError("Katalog stanica se ne moze otvoriti: %s" % error)
        if version != SCHEMA_VERSION:
            self._connection.close()
            raise CatalogError(
                "Pogresna verzija kataloga: %s (ocekivana %s)" % (version, SCHEMA_VERSION)
            )

    def close(self):
        self._connection.close()

    def meta(self):
        rows = self._connection.execute("SELECT key, value FROM meta").fetchall()
        return dict(rows)

    def channel_count(self):
        return self._connection.execute("SELECT COUNT(*) FROM channel").fetchone()[0]

    def find(self, key, limit):
        """Trazi stanice po kljucu (vidi app.utils.text.normalize_key).

        Svaka stanica se pominje jednom, sa nazivom po kome je najbolje
        pronadjena. Baca sqlite3.Error ako baza ne radi.
        """
        params = {"key": key, "upper": key + _MAX_CHAR, "limit": limit + 1}
        rows = self._connection.execute(_MAIN_SQL, params).fetchall()
        if not rows:
            rows = self._connection.execute(_CONTAINS_SQL, params).fetchall()
        truncated = len(rows) > limit
        return CatalogMatches(self._to_items(rows[:limit]), truncated)

    @staticmethod
    def _to_items(rows):
        return [
            (
                Channel(
                    id=row[0],
                    catalog_id=row[1],
                    name=row[2],
                    country_code=row[3],
                    country_name=row[4],
                    network=row[5],
                ),
                row[6],
            )
            for row in rows
        ]
