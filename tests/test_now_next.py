"""Testovi izracunavanja "Sada" i "Sledece". Podaci su IZMISLJENI."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.models.schedule import Programme  # noqa: E402
from app.services.now_next import compute_now_next  # noqa: E402

H = 3600


def p(title, start_h, end_h=None):
    return Programme(title, int(start_h * H), None if end_h is None else int(end_h * H))


A, B, C = p("A", 10, 11), p("B", 11, 12), p("C", 12, 13)


def test_empty_schedule():
    result = compute_now_next([], 10 * H)
    assert result.current is None and result.next is None


def test_before_first_programme_only_next():
    result = compute_now_next([A, B], 9 * H)
    assert result.current is None and result.next == A


def test_inside_a_programme():
    result = compute_now_next([A, B, C], int(10.5 * H))
    assert result.current == A and result.next == B
    assert result.current_end_utc == 11 * H and not result.current_end_derived
    assert result.progress == pytest.approx(0.5)


def test_exact_start_is_current_and_exact_end_is_not():
    assert compute_now_next([A, B], 10 * H).current == A
    result = compute_now_next([A, B], 11 * H)
    assert result.current == B and result.next is None


def test_last_programme_ended_means_nothing_is_on():
    result = compute_now_next([A, B], 12 * H)
    assert result.current is None and result.next is None


def test_gap_between_programmes():
    result = compute_now_next([p("A", 10, 11), p("B", 12, 13)], int(11.5 * H))
    assert result.current is None and result.next.title == "B"


def test_missing_end_is_derived_from_next_start():
    result = compute_now_next([p("A", 10), p("B", 12, 13)], 11 * H)
    assert result.current.title == "A" and result.current_end_derived
    assert result.current_end_utc == 12 * H
    assert result.progress == pytest.approx(0.5)


def test_last_programme_without_end_is_never_confirmed():
    result = compute_now_next([p("A", 10, 11), p("Z", 12)], 13 * H)
    assert result.current is None and result.next is None


def test_overlap_prefers_the_programme_that_started_last():
    result = compute_now_next([p("A", 10, 12), p("B", 11, 13)], int(11.5 * H))
    assert result.current.title == "B"


def test_overlap_where_the_later_one_is_short_leaves_a_hole():
    result = compute_now_next([p("A", 10, 14), p("B", 11, 11.5)], 12 * H)
    assert result.current is None  # B je zavrsena, a A se ne vraca


def test_next_can_be_after_midnight():
    day = [p("Nocni film", 23.5, 25.5), p("Sutra", 25.5, 26.5)]
    result = compute_now_next(day, int(23.75 * H))
    assert result.current.title == "Nocni film" and result.next.title == "Sutra"


def test_zero_length_programme_has_no_progress():
    result = compute_now_next([Programme("X", 100, 100), Programme("Y", 100, 200)], 100)
    assert result.current.title == "Y"
    result = compute_now_next([Programme("Z", 100, None), Programme("W", 100, None)], 100)
    assert result.current is None or result.progress is None


def test_progress_is_between_zero_and_one():
    for now in range(10 * H, 13 * H, 600):
        result = compute_now_next([A, B, C], now)
        assert result.current is not None
        assert 0 <= result.progress < 1
