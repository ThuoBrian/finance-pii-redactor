"""Unit tests for the shared accent-folding helper."""

from __future__ import annotations

from finance_redactor.domain.text_folding import fold_diacritics


def test_folds_common_accented_characters():
    assert fold_diacritics("José") == "Jose"
    assert fold_diacritics("Muñoz") == "Munoz"
    assert fold_diacritics("André") == "Andre"


def test_unaccented_text_is_unchanged():
    assert fold_diacritics("Jose Garcia") == "Jose Garcia"


def test_length_is_preserved():
    # The offset-safety invariant: spans found on a folded copy map back
    # exactly onto the original, unfolded text.
    samples = ["José García", "Müller GmbH", "plain ascii text", ""]
    for text in samples:
        assert len(fold_diacritics(text)) == len(text)


def test_case_is_left_alone():
    # Folding only strips accents; callers combine it with .lower()/.casefold()
    # themselves when case-insensitivity is also wanted.
    assert fold_diacritics("JOSÉ") == "JOSE"
