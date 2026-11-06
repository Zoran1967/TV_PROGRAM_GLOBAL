"""Sema kataloga stanica (read-only baza data/catalog_seed.db).

Koristi je i aplikacija (provera verzije) i alat tools/build_catalog.py
(pravljenje baze), da sema ostane na jednom mestu.
"""

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE country (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE channel (
    id           INTEGER PRIMARY KEY,
    catalog_id   TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    name_key     TEXT NOT NULL,
    country_code TEXT NOT NULL REFERENCES country(code),
    network      TEXT,
    timezone     TEXT,
    logo_url     TEXT
);

-- Svaki naziv se upisuje onoliko puta koliko ima reci: word_offset 0 je ceo
-- naziv, 1 je naziv bez prve reci itd. Tako pretraga po pocetku bilo koje reci
-- koristi indeks (npr. "one" pronalazi "BBC One").
CREATE TABLE channel_alias (
    channel_id  INTEGER NOT NULL REFERENCES channel(id),
    alias       TEXT NOT NULL,
    alias_key   TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('name', 'alt')),
    word_offset INTEGER NOT NULL,
    PRIMARY KEY (channel_id, alias_key)
);

CREATE INDEX idx_channel_alias_key ON channel_alias(alias_key);
"""


def create_schema(connection):
    connection.executescript(SCHEMA_SQL)
    connection.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
