"""Unit tests for alias/variant generation."""

from __future__ import annotations

import re

from finance_redactor.domain.aliases import aliases, name_pattern
from finance_redactor.domain.pseudonyms import normalize


def _compile(name: str) -> re.Pattern[str]:
    """Compile ``name_pattern`` the way the custom recognizer does."""
    return re.compile(rf"\b{name_pattern(name)}(?!\w)", re.IGNORECASE | re.UNICODE)


def _norm_aliases(name: str) -> set[str]:
    """Return normalized variants of ``name`` (case/whitespace-collapsed)."""
    return {normalize(v) for v in aliases(name)}


# --- aliases() -----------------------------------------------------------


def test_original_name_always_first():
    assert aliases("Acme Ltd")[0] == "Acme Ltd"


def test_suffix_equivalence_yields_long_form():
    norm = _norm_aliases("Acme Ltd")
    assert "acme ltd" in norm
    assert "acme limited" in norm


def test_long_form_input_yields_short_form():
    norm = _norm_aliases("Acme Limited")
    assert "acme ltd" in norm
    assert "acme limited" in norm


def test_period_variants_included():
    norm = _norm_aliases("Acme Ltd")
    assert "acme ltd." in norm
    assert "acme limited." in norm


def test_ampersand_and_swapped_both_ways():
    assert "smith and co" in _norm_aliases("Smith & Co")
    assert "smith & co" in _norm_aliases("Smith and Co")


def test_no_suffix_passthrough():
    # A name with no suffix and no ampersand has only itself as a variant.
    assert aliases("Brian Thuo") == ["Brian Thuo"]


def test_single_token_no_suffix():
    assert aliases("Safaricom") == ["Safaricom"]


def test_last_token_only_treated_as_suffix():
    # "Co" as the FIRST token is part of the name, not a suffix; only the last
    # token "Bank" is considered, and it isn't a suffix -> no Company variant.
    variants = aliases("Co Op Bank")
    assert variants == ["Co Op Bank"]
    assert not any("Company" in v for v in variants)


def test_co_as_last_token_is_suffix():
    assert "acme company" in _norm_aliases("Acme Co")


def test_no_middle_initial_changes():
    # Middle-initial handling is intentionally out of scope; the initial is preserved.
    assert aliases("Brian O. Thuo") == ["Brian O. Thuo"]


def test_llc_has_no_long_form_but_period_tolerant():
    norm = _norm_aliases("Acme LLC")
    assert "acme llc" in norm
    assert "acme llc." in norm
    assert not any("limited" in v for v in norm)


def test_empty_name_returns_empty():
    assert aliases("") == []
    assert aliases("   ") == []


def test_multiple_ampersands_full_cross_product():
    # Two ampersand tokens -> all four &/and combinations appear.
    norm = _norm_aliases("A & B & C")
    assert "a & b & c" in norm
    assert "a and b and c" in norm
    assert "a and b & c" in norm
    assert "a & b and c" in norm


def test_thailand_not_corrupted_by_and_swap():
    # "and" as a substring of "Thailand" must not be swapped.
    norm = _norm_aliases("Thailand Corp")
    assert "thail& corp" not in norm
    assert "thailand corp" in norm


# --- name_pattern() ------------------------------------------------------


def test_pattern_matches_suffix_equivalent():
    pat = _compile("Acme Ltd")
    assert pat.search("Paid Acme Limited in full")
    assert pat.search("Paid Acme Ltd in full")
    assert pat.search("Paid Acme Ltd. in full")


def test_pattern_does_not_over_match_bare_stem():
    pat = _compile("Acme Ltd")
    assert pat.search("Paid Acme in full") is None
    assert (
        pat.search("Paid Acme Limiteds in full") is None
    )  # "Limiteds" is not "Limited"
    assert pat.search("Paid AcmeLtd in full") is None  # no space between


def test_pattern_matches_ampersand_and():
    pat = _compile("Smith & Co")
    assert pat.search("Smith and Co invoice")
    assert pat.search("Smith & Co invoice")
    assert pat.search("Smith & Company invoice")


def test_pattern_is_case_insensitive():
    pat = _compile("Acme Ltd")
    assert pat.search("ACME LIMITED")
    assert pat.search("acme ltd")


def test_pattern_matches_at_end_of_string():
    pat = _compile("Acme Ltd")
    assert pat.search("Paid Acme Ltd")


def test_pattern_leading_word_boundary_prevents_partial_match():
    pat = _compile("Acme Ltd")
    assert pat.search("ReAcme Ltd") is None


def test_pattern_whitespace_flexible():
    pat = _compile("Acme Ltd")
    assert pat.search("Acme  Ltd")  # multiple spaces
