"""Testovi dijagnostike zastoja (bez Kivy-ja, bez pravih niti: vreme se zadaje rucno)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.utils.watchdog import MAX_ENTRIES, StallWatchdog, read_report  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _watchdog(tmp_path, clock):
    return StallWatchdog(str(tmp_path / "stalls.txt"), threshold=2.0, clock=clock, wall=lambda: 0)


def test_no_report_while_beats_keep_coming(tmp_path):
    clock = FakeClock()
    dog = _watchdog(tmp_path, clock)
    dog.start()
    for _ in range(10):
        clock.now += 1.0
        dog.beat()
        assert dog.check() is False
    dog.stop()
    assert read_report(str(tmp_path / "stalls.txt")) == ""


def test_stall_is_reported_once_and_its_end_is_recorded(tmp_path):
    clock = FakeClock()
    dog = _watchdog(tmp_path, clock)
    dog.start()
    clock.now += 3.0
    assert dog.check() is True
    assert dog.check() is False  # isti zastoj se ne upisuje dvaput
    clock.now += 4.0
    dog.beat()
    dog.stop()
    report = read_report(str(tmp_path / "stalls.txt"))
    assert "zastoj 3.0 s" in report and "glavna nit" in report
    assert "kraj zastoja: glavna nit je stajala 7.0 s" in report


def test_pause_does_not_count_as_a_stall(tmp_path):
    clock = FakeClock()
    dog = _watchdog(tmp_path, clock)
    dog.start()
    dog.pause()
    clock.now += 60.0
    assert dog.check() is False
    dog.resume()
    clock.now += 1.0
    assert dog.check() is False
    dog.stop()


def test_only_latest_entries_are_kept(tmp_path):
    clock = FakeClock()
    dog = _watchdog(tmp_path, clock)
    dog.start()
    for _ in range(MAX_ENTRIES + 5):
        clock.now += 3.0
        assert dog.check() is True
        dog.beat()
    dog.stop()
    path = str(tmp_path / "stalls.txt")
    from app.utils.watchdog import read_entries
    assert len(read_entries(path)) == MAX_ENTRIES


def test_unwritable_path_never_raises(tmp_path):
    clock = FakeClock()
    blocked = tmp_path / "file"
    blocked.write_text("x")
    dog = StallWatchdog(str(blocked / "stalls.txt"), threshold=2.0, clock=clock)
    dog.start()
    clock.now += 5.0
    dog.check()
    dog.beat()
    dog.stop()
