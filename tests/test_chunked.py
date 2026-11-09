"""Testovi postepenog pravljenja liste (bez Kivy-ja: sat i lista su lazni)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.utils.chunked import ChunkedFiller  # noqa: E402


class FakeEvent:
    def __init__(self, function):
        self.function = function
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeClock:
    def __init__(self):
        self.queue = []

    def schedule_once(self, function, _delay=0):
        event = FakeEvent(function)
        self.queue.append(event)
        return event

    def frame(self):
        queue, self.queue = self.queue, []
        for event in queue:
            if not event.cancelled:
                event.function(0)


class FakeList:
    def __init__(self):
        self.children = []

    def add_widget(self, widget):
        self.children.append(widget)


def builders(count, start=0):
    return (lambda number=number: number for number in range(start, start + count))


def filler(clock, first_batch=12):
    return ChunkedFiller(first_batch=first_batch, frame_budget=0.0, clock=clock)


def test_first_batch_is_immediate_and_the_rest_comes_in_later_frames(monkeypatch):
    monkeypatch.delenv("TVPG_SYNC_UI", raising=False)
    clock, target, done = FakeClock(), FakeList(), []
    filler(clock).fill(target, builders(50), on_done=lambda: done.append(1))
    assert len(target.children) == 12 and not done
    for _ in range(100):
        if done:
            break
        clock.frame()
    assert target.children == list(range(50)) and done == [1]


def test_sync_mode_builds_everything_at_once(monkeypatch):
    monkeypatch.setenv("TVPG_SYNC_UI", "1")
    clock, target, done = FakeClock(), FakeList(), []
    filler(clock).fill(target, builders(50), on_done=lambda: done.append(1))
    assert len(target.children) == 50 and done == [1] and not clock.queue


def test_new_fill_cancels_the_old_one(monkeypatch):
    monkeypatch.delenv("TVPG_SYNC_UI", raising=False)
    clock, target = FakeClock(), FakeList()
    worker = filler(clock)
    worker.fill(target, builders(50))
    target.children.clear()
    worker.fill(target, builders(30, start=100))
    for _ in range(100):
        clock.frame()
    assert target.children == list(range(100, 130))


def test_cancel_stops_building(monkeypatch):
    monkeypatch.delenv("TVPG_SYNC_UI", raising=False)
    clock, target, done = FakeClock(), FakeList(), []
    worker = filler(clock)
    worker.fill(target, builders(50), on_done=lambda: done.append(1))
    worker.cancel()
    for _ in range(10):
        clock.frame()
    assert len(target.children) == 12 and not done


def test_broken_item_is_skipped(monkeypatch):
    monkeypatch.delenv("TVPG_SYNC_UI", raising=False)

    def broken():
        raise RuntimeError("x")

    clock, target, done = FakeClock(), FakeList(), []
    filler(clock).fill(target, [lambda: 1, broken, lambda: 3], on_done=lambda: done.append(1))
    assert target.children == [1, 3] and done == [1]
