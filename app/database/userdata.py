"""Trajni korisnicki podaci (SQLite, upisiva baza u folderu aplikacije).

Cuva tri stvari:
  * omiljene stanice (po catalog_id, koji ostaje isti kad se katalog osvezi);
  * poslednji uspesno preuzet raspored po stanici kod izvora (da radi bez mreze);
  * podesavanja aplikacije (jezik, tema, vreme, osvezavanje) kao parove kljuc-vrednost.

Baza se koristi iz vise niti (UI nit i pozadinsko preuzimanje), pa su svi pozivi
iza jedne brave. Svaka greska baze se prijavljuje kao UserDataError; pozivaoc
odlucuje sta da radi (aplikacija nastavlja da radi bez trajnog cuvanja).
"""

import json
import logging
import os
import sqlite3
import threading
import time

from app.models.schedule import Programme

LOGGER = logging.getLogger(__name__)

USER_SCHEMA_VERSION = 2
DEFAULT_FILE_NAME = "userdata.db"
# Najvise rasporeda u trajnom kesu i koliko dugo se cuvaju
CACHE_MAX_ENTRIES = 100
CACHE_MAX_AGE_SECONDS = 14 * 24 * 3600

_SCHEMA_SQL = """
CREATE TABLE favourite (
    catalog_id TEXT PRIMARY KEY,
    added_at   INTEGER NOT NULL
);

CREATE TABLE schedule_cache (
    source_id         TEXT NOT NULL,
    source_channel_id TEXT NOT NULL,
    fetched_at        INTEGER NOT NULL,
    payload           TEXT NOT NULL,
    PRIMARY KEY (source_id, source_channel_id)
);
"""

# Verzija 2 (Faza 7): podesavanja. Baza verzije 1 se samo dopunjuje, podaci ostaju.
_SETTING_SQL = """
CREATE TABLE IF NOT EXISTS setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class UserDataError(Exception):
    """Baza korisnickih podataka ne radi (ne otvara se, nova je verzija, greska upisa)."""


class UserDatabase:
    def __init__(self, path, clock=time.time):
        self._path = path
        self._clock = clock
        self._lock = threading.RLock()
        self._connection = self._open_with_recovery(path)

    # ---- otvaranje ---------------------------------------------------------

    @classmethod
    def default_path(cls, directory):
        return os.path.join(directory, DEFAULT_FILE_NAME)

    def _open_with_recovery(self, path):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        except OSError as error:
            raise UserDataError("Folder za podatke nije dostupan: %s" % error)
        try:
            return self._open(path)
        except sqlite3.DatabaseError as error:
            if isinstance(error, sqlite3.OperationalError) and "locked" in str(error).lower():
                raise UserDataError("Baza korisnickih podataka je zakljucana: %s" % error)
            # Ostecen fajl: sacuvaj ga pod drugim imenom (ne brise se) i napravi novi
            backup = "%s.corrupt-%d" % (path, int(self._clock()))
            LOGGER.error("Baza korisnickih podataka je ostecena (%s); premestena u %s", error, backup)
            try:
                os.replace(path, backup)
            except OSError as move_error:
                raise UserDataError("Ostecena baza se ne moze premestiti: %s" % move_error)
            try:
                return self._open(path)
            except sqlite3.Error as retry_error:
                raise UserDataError("Nova baza se ne moze napraviti: %s" % retry_error)
        except sqlite3.Error as error:
            raise UserDataError("Baza korisnickih podataka se ne moze otvoriti: %s" % error)

    @staticmethod
    def _open(path):
        connection = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                has_tables = connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                ).fetchone()[0]
                if has_tables:
                    raise sqlite3.DatabaseError("nepoznata baza bez oznake verzije")
                with connection:
                    connection.executescript(_SCHEMA_SQL + _SETTING_SQL)
                    connection.execute("PRAGMA user_version = %d" % USER_SCHEMA_VERSION)
            elif version == 1:
                with connection:
                    connection.executescript(_SETTING_SQL)
                    connection.execute("PRAGMA user_version = %d" % USER_SCHEMA_VERSION)
            elif version != USER_SCHEMA_VERSION:
                raise UserDataError(
                    "Baza korisnickih podataka ima verziju %s (ocekivana %s)"
                    % (version, USER_SCHEMA_VERSION)
                )
        except Exception:
            connection.close()
            raise
        return connection

    def close(self):
        with self._lock:
            self._connection.close()

    # ---- pomocno -----------------------------------------------------------

    def _run(self, action):
        with self._lock:
            try:
                return action(self._connection)
            except sqlite3.Error as error:
                raise UserDataError("Greska baze korisnickih podataka: %s" % error)

    # ---- omiljene stanice --------------------------------------------------

    def add_favourite(self, catalog_id):
        now = int(self._clock())

        def action(connection):
            with connection:
                connection.execute(
                    "INSERT OR IGNORE INTO favourite (catalog_id, added_at) VALUES (?, ?)",
                    (catalog_id, now),
                )

        self._run(action)

    def remove_favourite(self, catalog_id):
        def action(connection):
            with connection:
                connection.execute("DELETE FROM favourite WHERE catalog_id = ?", (catalog_id,))

        self._run(action)

    def is_favourite(self, catalog_id):
        return self._run(
            lambda connection: connection.execute(
                "SELECT 1 FROM favourite WHERE catalog_id = ?", (catalog_id,)
            ).fetchone()
            is not None
        )

    def favourite_ids(self):
        """catalog_id svih omiljenih, od najranije dodate."""
        return self._run(
            lambda connection: [
                row[0]
                for row in connection.execute(
                    "SELECT catalog_id FROM favourite ORDER BY added_at, catalog_id"
                )
            ]
        )

    # ---- podesavanja -------------------------------------------------------

    def load_settings(self):
        """Svi sacuvani parovi kljuc-vrednost (proveru vrednosti radi pozivalac)."""
        return self._run(
            lambda connection: dict(connection.execute("SELECT key, value FROM setting"))
        )

    def save_setting(self, key, value):
        def action(connection):
            with connection:
                connection.execute(
                    "INSERT OR REPLACE INTO setting (key, value) VALUES (?, ?)", (key, value)
                )

        self._run(action)

    # ---- trajni kes rasporeda ----------------------------------------------

    def save_schedule(self, source_id, source_channel_id, fetched_at, programmes):
        payload = json.dumps(
            [
                [p.title, p.start_utc, p.end_utc, p.description, p.category]
                for p in programmes
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        now = int(self._clock())

        def action(connection):
            with connection:
                connection.execute(
                    "INSERT OR REPLACE INTO schedule_cache"
                    " (source_id, source_channel_id, fetched_at, payload) VALUES (?, ?, ?, ?)",
                    (source_id, source_channel_id, int(fetched_at), payload),
                )
                connection.execute(
                    "DELETE FROM schedule_cache WHERE fetched_at < ?",
                    (now - CACHE_MAX_AGE_SECONDS,),
                )
                connection.execute(
                    "DELETE FROM schedule_cache WHERE rowid NOT IN ("
                    " SELECT rowid FROM schedule_cache ORDER BY fetched_at DESC LIMIT ?)",
                    (CACHE_MAX_ENTRIES,),
                )

        self._run(action)

    def load_schedule(self, source_id, source_channel_id):
        """(fetched_at, [Programme]) ili None ako nema sacuvanog rasporeda.

        Neispravan sadrzaj se brise i vraca se None (kes se moze ponovo preuzeti).
        """
        row = self._run(
            lambda connection: connection.execute(
                "SELECT fetched_at, payload FROM schedule_cache"
                " WHERE source_id = ? AND source_channel_id = ?",
                (source_id, source_channel_id),
            ).fetchone()
        )
        if row is None:
            return None
        try:
            programmes = _decode_programmes(row[1])
        except (ValueError, TypeError, IndexError):
            LOGGER.warning("Sacuvan raspored %s/%s je neispravan; brise se", source_id, source_channel_id)
            self.delete_schedule(source_id, source_channel_id)
            return None
        return int(row[0]), programmes

    def delete_schedule(self, source_id, source_channel_id):
        def action(connection):
            with connection:
                connection.execute(
                    "DELETE FROM schedule_cache WHERE source_id = ? AND source_channel_id = ?",
                    (source_id, source_channel_id),
                )

        self._run(action)

    def schedule_count(self):
        return self._run(
            lambda connection: connection.execute("SELECT COUNT(*) FROM schedule_cache").fetchone()[0]
        )


def _decode_programmes(payload):
    items = json.loads(payload)
    if not isinstance(items, list):
        raise ValueError("ocekivana lista")
    programmes = []
    for item in items:
        title, start, end, description, category = item
        if not isinstance(title, str) or not title or isinstance(start, bool) or not isinstance(start, int):
            raise ValueError("neispravna emisija")
        if end is not None and (isinstance(end, bool) or not isinstance(end, int)):
            raise ValueError("neispravan kraj")
        if description is not None and not isinstance(description, str):
            raise ValueError("neispravan opis")
        if category is not None and not isinstance(category, str):
            raise ValueError("neispravna kategorija")
        programmes.append(Programme(title, start, end, description, category))
    return programmes
