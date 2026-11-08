"""Dijagnostika zastoja: pamti gde je glavna nit stala kad aplikacija prestane da reaguje.

Glavna nit javlja "otkucaj" (beat) nekoliko puta u sekundi. Pozadinska nit proverava da li je
poslednji otkucaj stariji od praga; ako jeste, upisuje u fajl gde se glavna nit u tom trenutku
nalazi (poslednji pozivi funkcija) i sta rade ostale niti. Fajl ostaje i posle zatvaranja
aplikacije, pa se prikaz u Podesavanjima vidi i posle "ne reaguje".

Bez Kivy-ja, da se lako testira.
"""

import os
import sys
import threading
import time
import traceback

MAX_ENTRIES = 8
MAX_REPORT_CHARS = 1800
SEPARATOR = "\n--\n"


def _short(path):
    return os.path.basename(path or "?")


def _stack_lines(frame, depth):
    entries = traceback.extract_stack(frame)[-depth:]
    return ["%s:%d %s" % (_short(item.filename), item.lineno, item.name) for item in entries]


class StallWatchdog:
    def __init__(self, path, threshold=2.0, poll=0.5, clock=time.monotonic, wall=time.time):
        self._path = path
        self._threshold = threshold
        self._poll = poll
        self._clock = clock
        self._wall = wall
        self._lock = threading.Lock()
        self._main_ident = None
        self._last_beat = clock()
        self._paused = False
        self._open_since = None  # kad je poceo zastoj koji je upisan, a jos nije zavrsen
        self._thread = None
        self._stop = threading.Event()
        self.on_report = None  # funkcija bez argumenata; zove se iz pozadinske niti

    # ---- glavna nit --------------------------------------------------------

    def start(self, main_ident=None):
        self._main_ident = main_ident or threading.get_ident()
        self._last_beat = self._clock()
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="stall-watchdog", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def beat(self):
        now = self._clock()
        with self._lock:
            since = self._open_since
            self._open_since = None
            self._last_beat = now
        if since is not None:
            self._append("kraj zastoja: glavna nit je stajala %.1f s" % (now - since))

    def pause(self):
        with self._lock:
            self._paused = True

    def resume(self):
        with self._lock:
            self._paused = False
            self._last_beat = self._clock()
            self._open_since = None

    # ---- pozadinska nit --------------------------------------------------------

    def _run(self):
        while not self._stop.wait(self._poll):
            try:
                self.check()
            except Exception:  # dijagnostika nikad ne sme da smeta aplikaciji
                pass

    def check(self):
        """Jedna provera; vraca True ako je upisan novi zastoj."""
        now = self._clock()
        with self._lock:
            if self._paused or self._open_since is not None:
                return False
            gap = now - self._last_beat
            if gap < self._threshold:
                return False
            self._open_since = self._last_beat
        self._append(self._describe(gap))
        return True

    def _describe(self, gap):
        stamp = time.strftime("%d.%m. %H:%M:%S", time.localtime(self._wall()))
        lines = ["%s zastoj %.1f s; glavna nit:" % (stamp, gap)]
        frames = sys._current_frames()
        main = frames.get(self._main_ident)
        if main is not None:
            lines.extend("  " + text for text in _stack_lines(main, 7))
        names = {thread.ident: thread.name for thread in threading.enumerate()}
        for ident, frame in frames.items():
            if ident in (self._main_ident, threading.get_ident()):
                continue
            lines.append("nit %s:" % names.get(ident, ident))
            lines.extend("  " + text for text in _stack_lines(frame, 3))
        return "\n".join(lines)

    # ---- fajl --------------------------------------------------------------

    def _append(self, text):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
            entries = read_entries(self._path)
            entries.append(text)
            with open(self._path, "w", encoding="utf-8") as handle:
                handle.write(SEPARATOR.join(entries[-MAX_ENTRIES:]))
        except OSError:
            return
        callback = self.on_report
        if callback is not None:
            try:
                callback()
            except Exception:
                pass


def read_entries(path):
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return []
    return [part for part in text.split(SEPARATOR) if part.strip()]


def read_report(path, limit=MAX_REPORT_CHARS):
    """Poslednji upisani zastoji (najnoviji na kraju), skraceni na limit znakova."""
    text = SEPARATOR.join(read_entries(path))
    return text[-limit:] if len(text) > limit else text
