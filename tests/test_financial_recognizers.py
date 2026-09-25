"""Tests for bank/payment detection: the labelled recognizers and the PDF detector.

Every value here is synthetic: Visa's published test card, the IBAN example
from the IBAN registry, made-up Kenyan account and paybill numbers, and a
fictional BIC.
"""

from __future__ import annotations

import pytest

from finance_redactor.config import DEFAULT_SETTINGS
from finance_redactor.domain.entities import DetectionSource
from finance_redactor.infrastructure.detection.financial_recognizers import (
    build_financial_recognizers,
)
from finance_redactor.infrastructure.detection.pattern_detector import (
    PatternDetector,
)

_LABELLED = ["KE_BANK_ACCOUNT", "MPESA_NUMBER", "SWIFT_CODE"]


def _matches(text: str) -> list[tuple[str, str]]:
    return [
        (r.entity_type, text[r.start : r.end])
        for recognizer in build_financial_recognizers()
        for r in recognizer.analyze(text, _LABELLED)
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A/C No: 0123456789", ("KE_BANK_ACCOUNT", "0123456789")),
        ("Account Number 0123-4567-8901", ("KE_BANK_ACCOUNT", "0123-4567-8901")),
        ("ACC NO.00112233445", ("KE_BANK_ACCOUNT", "00112233445")),
        ("Paybill 123456", ("MPESA_NUMBER", "123456")),
        ("Till No. 54321", ("MPESA_NUMBER", "54321")),
        ("M-Pesa: 7654321", ("MPESA_NUMBER", "7654321")),
        ("SWIFT code: TESTKENA", ("SWIFT_CODE", "TESTKENA")),
        ("BIC TESTKENAXXX", ("SWIFT_CODE", "TESTKENAXXX")),
    ],
)
def test_labelled_value_is_matched_without_its_label(text, expected) -> None:
    assert _matches(text) == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "Invoice 0123456789",  # no label: could be any reference number
        "Staff ID 10010",
        "Accounts 2024 budget 12345678",  # "Accounts" is not an account label
        "swift is fast",
        "SWIFT code: testkena",  # BICs are uppercase
    ],
)
def test_unlabelled_or_lookalike_values_are_not_matched(text) -> None:
    assert _matches(text) == []


def test_recognizer_respects_the_requested_entities() -> None:
    text = "A/C No: 0123456789, Paybill 123456"
    only_mpesa = [
        r.entity_type
        for recognizer in build_financial_recognizers()
        for r in recognizer.analyze(text, ["MPESA_NUMBER"])
    ]
    assert only_mpesa == ["MPESA_NUMBER"]


def test_pdf_detector_finds_every_financial_type_as_a_pattern_match() -> None:
    text = (
        "Card 4111 1111 1111 1111, IBAN GB82 WEST 1234 5698 7654 32, "
        "A/C No: 0123456789, Paybill 123456, SWIFT TESTKENA"
    )
    detections = PatternDetector().analyze(
        text, list(DEFAULT_SETTINGS.fixed_masks), 0.4
    )

    assert {d.entity_type: d.text for d in detections} == {
        "CREDIT_CARD": "4111 1111 1111 1111",
        "IBAN_CODE": "GB82 WEST 1234 5698 7654 32",
        "KE_BANK_ACCOUNT": "0123456789",
        "MPESA_NUMBER": "123456",
        "SWIFT_CODE": "TESTKENA",
    }
    assert {d.source for d in detections} == {DetectionSource.PATTERN}


def test_pdf_detector_rejects_a_card_number_that_fails_luhn() -> None:
    detections = PatternDetector().analyze(
        "Card 4111 1111 1111 1112", ["CREDIT_CARD"], 0.4
    )
    assert detections == []
