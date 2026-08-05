"""Unit tests for the typo-tolerant suggestion fallback."""

from __future__ import annotations

from finance_redactor.domain.fuzzy import closest_match


def test_finds_close_typo_match():
    result = closest_match("micheal mugo", ["michael mugo", "jane doe"], 0.84)

    assert result is not None
    name, score = result
    assert name == "michael mugo"
    assert score >= 0.84


def test_no_match_below_threshold():
    assert closest_match("someone else entirely", ["michael mugo"], 0.84) is None


def test_no_candidates_returns_none():
    assert closest_match("michael mugo", [], 0.84) is None


def test_length_delta_guard_skips_unrelated_candidates():
    # "co" is a substring-similar but wildly different-length candidate; the
    # length guard should skip comparing it at all rather than let a short
    # string's high ratio-per-character sneak past the threshold.
    assert closest_match("company", ["co"], 0.5) is None


def test_picks_the_closest_of_several_candidates():
    result = closest_match(
        "micheal mugo", ["mitchell mugo", "michael mugo", "someone else"], 0.5
    )

    assert result is not None
    name, _ = result
    assert name == "michael mugo"
