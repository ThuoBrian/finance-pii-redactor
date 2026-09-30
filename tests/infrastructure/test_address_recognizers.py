"""Tests for the postal/street address recognizer. Every address is made up."""

from __future__ import annotations

import pytest

from finance_redactor.infrastructure.detection.address_recognizers import (
    build_address_recognizers,
)


def _matches(text: str) -> list[str]:
    return [
        text[r.start : r.end]
        for recognizer in build_address_recognizers()
        for r in recognizer.analyze(text, ["ADDRESS"])
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Send to P.O. Box 12345-00100, Springfield today",
            ["P.O. Box 12345-00100, Springfield"],
        ),
        ("P O BOX 4521 SHELBYVILLE", ["P O BOX 4521 SHELBYVILLE"]),
        ("PO Box 88", ["PO Box 88"]),
        ("Private Bag 77", ["Private Bag 77"]),
        ("Box 555-00200", ["Box 555-00200"]),
        ("Plot No. 7, Maple Rd.", ["Plot No. 7", "Maple Rd."]),
        ("L.R. No. 209/1234", ["L.R. No. 209/1234"]),
        ("House 12B", ["House 12B"]),
        ("PLOT 44", ["PLOT 44"]),
        ("14 Maple Road", ["14 Maple Road"]),
        ("Paid at Elm Avenue branch", ["Elm Avenue"]),
        ("OAK TREE AVENUE", ["OAK TREE AVENUE"]),
        ("22 Riverside Drive", ["22 Riverside Drive"]),
        ("9 Willow Close", ["9 Willow Close"]),
    ],
)
def test_address_is_matched(text: str, expected: list[str]) -> None:
    assert _matches(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Box 5 of the form",  # a bare box number needs a postcode
        "in-house 2024 training",  # lowercase "house" is not a label
        "the road was closed",  # lowercase suffixes are prose
        "Year End Close",  # weak suffix without a house number
        "Donation Drive",
        "St. Mary's school",  # bare "St" is never a suffix
        "Invoice 0123456789",
        "Springfield",  # plain place names are left alone by design
    ],
)
def test_non_address_is_not_matched(text: str) -> None:
    assert _matches(text) == []


def test_recognizer_respects_the_requested_entities() -> None:
    [recognizer] = build_address_recognizers()
    assert recognizer.analyze("P.O. Box 12", ["KE_BANK_ACCOUNT"]) == []
