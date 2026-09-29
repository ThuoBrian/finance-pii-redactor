"""Unit tests for the custom name recognizer's alias-aware matching.

These exercise :class:`CustomNameRecognizer.analyze` directly (no ``AnalyzerEngine``,
no spaCy model) to confirm variant surface forms are detected and non-variants are not.
"""

from __future__ import annotations

import time

from finance_redactor.infrastructure.detection.custom_recognizer import (
    CustomNameRecognizer,
)


def _org(names: list[str]) -> CustomNameRecognizer:
    return CustomNameRecognizer("ORGANIZATION", names, score=0.9)


def test_detects_suffix_equivalent_long_form():
    rec = _org(["Acme Ltd"])
    hits = rec.analyze("Paid Acme Limited in full", ["ORGANIZATION"], None)
    assert len(hits) == 1
    assert hits[0].start == 5
    assert hits[0].end == 17  # spans "Acme Limited"


def test_detects_short_form_and_period():
    rec = _org(["Acme Ltd"])
    assert rec.analyze("Paid Acme Ltd in full", ["ORGANIZATION"], None)
    assert rec.analyze("Paid Acme Ltd. in full", ["ORGANIZATION"], None)


def test_does_not_match_bare_stem():
    rec = _org(["Acme Ltd"])
    assert rec.analyze("Paid Acme in full", ["ORGANIZATION"], None) == []


def test_detects_ampersand_and_swap():
    rec = _org(["Smith & Co"])
    hits = rec.analyze("Smith and Co invoice", ["ORGANIZATION"], None)
    assert len(hits) == 1
    assert rec.analyze("Smith & Co invoice", ["ORGANIZATION"], None)
    assert rec.analyze("Smith & Company invoice", ["ORGANIZATION"], None)


def test_case_insensitive_match():
    rec = _org(["Acme Ltd"])
    assert rec.analyze("ACME LIMITED", ["ORGANIZATION"], None)


def test_multiple_occurrences_all_detected():
    rec = _org(["Acme Ltd"])
    hits = rec.analyze("Acme Ltd and Acme Limited", ["ORGANIZATION"], None)
    assert len(hits) == 2


def test_unrelated_text_no_hits():
    rec = _org(["Acme Ltd"])
    assert rec.analyze("Nothing to see here", ["ORGANIZATION"], None) == []


def test_entity_filter_skips_when_not_requested():
    rec = _org(["Acme Ltd"])
    assert rec.analyze("Acme Ltd", ["PERSON"], None) == []


def test_score_is_the_injected_value():
    rec = _org(["Acme Ltd"])
    hits = rec.analyze("Acme Ltd", ["ORGANIZATION"], None)
    assert hits[0].score == 0.9


def test_matches_across_irregular_whitespace():
    r"""The automaton matches literal keys, so irregular spacing in the haystack
    text must be collapsed before matching (mirrors the old regex's ``\\s+``
    flexibility between name tokens).
    """
    rec = _org(["Acme Ltd"])
    hits = rec.analyze("Paid   Acme    Ltd   today", ["ORGANIZATION"], None)
    assert len(hits) == 1


def test_scales_with_text_length_not_dictionary_size():
    """Guard against regressing to the old per-name regex loop.

    That approach cost one regex scan per loaded name, so analyzing one text
    against the real ~26.5k-row master list took ~64ms. The Aho-Corasick
    automaton scans the text once regardless of dictionary size. Uses a
    synthetic 20k-name list (the real master list is gitignored, so CI has no
    access to it) and asserts comfortably below the old per-call cost.
    """
    names = [f"Synthetic Vendor {i} Ltd" for i in range(20_000)]
    rec = _org(names)
    text = "Paid Synthetic Vendor 12345 Ltd for services rendered on invoice 1029."
    assert rec.analyze(text, ["ORGANIZATION"], None)

    start = time.perf_counter()
    for _ in range(20):
        rec.analyze(text, ["ORGANIZATION"], None)
    elapsed_per_call = (time.perf_counter() - start) / 20
    assert elapsed_per_call < 0.02
