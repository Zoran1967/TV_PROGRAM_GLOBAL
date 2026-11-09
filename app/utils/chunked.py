"""Postepeno pravljenje dugackih lista (da glavna nit ne zastane i Android ne javi "ne reaguje").

Pravljenje KivyMD stavki je sporo na telefonu: stotinak stavki odjednom blokira aplikaciju
desetak sekundi. ChunkedFiller dodaje prvih nekoliko stavki odmah (ekran se odmah popuni), a ostatak
po kadrovima, uz vremenski budzet po kadru.

Promenljiva okruzenja TVPG_SYNC_UI=1 (samo za testove) pravi celu listu odmah, bez kadrova.
"""

import logging
import os
import time

_LOGGER = logging.getLogger(__name__)

FIRST_BATCH = 12
FRAME_BUDGET = 0.012


def sync_mode():
    return os.environ.get("TVPG_SYNC_UI") == "1"


class ChunkedFiller:
    def __init__(self, first_batch=FIRST_BATCH, frame_budget=FRAME_BUDGET, clock=None):
        self._first_batch = first_batch
        self._frame_budget = frame_budget
        self._clock = clock  # za testove; inace Kivy Clock
        self._build_id = 0
        self._event = None

    def cancel(self):
        """Prekida pravljenje koje je u toku (vec dodate stavke ostaju)."""
        self._build_id += 1
        if self._event is not None:
            self._event.cancel()
            self._event = None

    def _get_clock(self):
        if self._clock is None:
            from kivy.clock import Clock  # kasni uvoz: modul se testira i bez Kivy-ja

            self._clock = Clock
        return self._clock

    def fill(self, container, builders, on_done=None):
        """Dodaje u container stavke koje prave funkcije iz builders (po jedna po stavci)."""
        self.cancel()
        build_id = self._build_id
        iterator = iter(builders)
        limit = None if sync_mode() else self._first_batch

        def step(first):
            if build_id != self._build_id:
                return  # u medjuvremenu je zapoceto novo pravljenje ili je prekinuto
            started = time.perf_counter()
            added = 0
            for make in iterator:
                try:
                    container.add_widget(make())
                except Exception:  # jedna pokvarena stavka ne sme da sruši aplikaciju
                    _LOGGER.exception("Stavka liste nije napravljena")
                    continue
                added += 1
                if limit is None and first:
                    continue  # sinhroni rezim: sve odmah
                if first:
                    if added >= limit:
                        break
                elif time.perf_counter() - started >= self._frame_budget:
                    break
            else:
                self._event = None
                if on_done is not None:
                    on_done()
                return
            self._event = self._get_clock().schedule_once(lambda _dt: step(False), 0)

        step(True)
