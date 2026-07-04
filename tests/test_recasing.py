"""Unit tests for the ALL-CAPS recasing helper."""

from __future__ import annotations

from finance_redactor.infrastructure.detection.recasing import recase_uppercase


def test_recases_all_caps_name():
    assert (
        recase_uppercase("Payment - MARY WANJIRU expense")
        == "Payment - Mary Wanjiru expense"
    )


def test_length_is_preserved():
    # The offset-safety invariant: spans on the recased copy map back exactly.
    samples = [
        "Payment - MARY WANJIRU expense reimbursement",
        "USD 500 to KCB BANK",
        "MÜLLER GMBH",
        "plain mixed case text",
    ]
    for text in samples:
        assert len(recase_uppercase(text)) == len(text)


def test_single_letter_caps_unchanged():
    assert recase_uppercase("I met A B today") == "I met A B today"


def test_mixed_case_and_clean_text_unchanged():
    assert recase_uppercase("Mary Wanjiru paid Safaricom") == (
        "Mary Wanjiru paid Safaricom"
    )


def test_alphanumeric_tokens_unchanged():
    # Tokens mixing letters and digits are not purely alphabetic -> left as-is.
    assert recase_uppercase("INV2024 paid R2D2") == "INV2024 paid R2D2"


def test_standalone_acronym_is_recased():
    # Documents the accepted trade-off: a standalone all-caps alpha token is
    # recased in the copy (may yield a reviewable false positive downstream).
    assert recase_uppercase("paid KCB today") == "paid Kcb today"


def test_accented_uppercase_recased_same_length():
    out = recase_uppercase("MÜLLER")
    assert out == "Müller"
    assert len(out) == len("MÜLLER")
