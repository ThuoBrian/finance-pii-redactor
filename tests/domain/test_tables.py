"""Tests for table columns: grouping OCR lines, header keys, cell detections.

All names and numbers here are made up.
"""

from __future__ import annotations

from finance_redactor.domain.entities import CUSTOM_ENTITY_TYPE, DetectionSource
from finance_redactor.domain.ocr import OcrLine
from finance_redactor.domain.tables import (
    TableColumn,
    column_detections,
    column_key,
    columns_from_lines,
    header_or_default,
    suggested_columns,
)

# Column x-ranges of a three-column table, in rendered-page pixels.
_PAYEE, _ACCOUNT, _AMOUNT = (100.0, 300.0), (350.0, 500.0), (550.0, 650.0)


def _line(text: str, band: tuple[float, float], row: int) -> OcrLine:
    top = 100.0 + row * 30.0
    return OcrLine(text, (band[0], top, band[1], top + 20.0), 0.95)


def _grid() -> list[OcrLine]:
    return [
        _line("Payee", _PAYEE, 0),
        _line("Account No", _ACCOUNT, 0),
        _line("Amount", _AMOUNT, 0),
        _line("Alex Sample", _PAYEE, 1),
        _line("1234567890", _ACCOUNT, 1),
        _line("100.00", _AMOUNT, 1),
        _line("Robin Example", _PAYEE, 2),
        _line("2345678901", _ACCOUNT, 2),
        _line("250.00", _AMOUNT, 2),
    ]


def test_ocr_lines_in_a_grid_become_columns_with_headers() -> None:
    columns = columns_from_lines(_grid())

    assert columns == [
        TableColumn("Payee", ("Alex Sample", "Robin Example")),
        TableColumn("Account No", ("1234567890", "2345678901")),
        TableColumn("Amount", ("100.00", "250.00")),
    ]


def test_lines_given_in_any_order_still_form_the_table() -> None:
    assert columns_from_lines(list(reversed(_grid()))) == columns_from_lines(_grid())


def test_a_paragraph_is_not_a_table() -> None:
    lines = [_line(f"Sentence number {i}", (100.0, 600.0), i) for i in range(5)]

    assert columns_from_lines(lines) == []


def test_a_header_and_one_row_is_too_small_to_be_a_table() -> None:
    assert columns_from_lines(_grid()[:6]) == []


def test_a_wrapped_cell_inside_the_table_does_not_end_it() -> None:
    lines = _grid()[:6] + [
        _line("Ltd", _PAYEE, 2),  # the payee wrapped onto its own row
        _line("Robin Example", _PAYEE, 3),
        _line("2345678901", _ACCOUNT, 3),
        _line("250.00", _AMOUNT, 3),
    ]

    payee = columns_from_lines(lines)[0]

    assert payee.cells == ("Alex Sample", "Ltd", "Robin Example")


def test_a_line_straddling_two_columns_joins_the_one_it_overlaps_most() -> None:
    lines = [*_grid(), _line("Sam Placeholder Trading", (100.0, 400.0), 3)]
    lines.append(_line("3456789012", (420.0, 500.0), 3))

    payee = columns_from_lines(lines)[0]

    assert "Sam Placeholder Trading" in payee.cells


def test_header_or_default_numbers_a_blank_header() -> None:
    assert header_or_default(None, 0) == "Column 1"
    assert header_or_default("  ", 2) == "Column 3"
    assert header_or_default(" Payee ", 0) == "Payee"


def test_column_key_merges_the_same_header_across_pages() -> None:
    assert column_key("Account  No") == column_key("account no")


def test_name_account_and_contact_columns_are_suggested() -> None:
    keys = ["payee", "account no", "amount", "date", "phone", "paid to", "a/c"]

    assert suggested_columns(keys) == {
        "payee",
        "account no",
        "phone",
        "paid to",
        "a/c",
    }


def test_column_detections_finds_only_the_chosen_columns_cells() -> None:
    text = "Payee Amount\nAlex Sample 100.00\nRobin Example 250.00"
    columns = [
        TableColumn("Payee", ("Alex Sample", "Robin Example")),
        TableColumn("Amount", ("100.00", "250.00")),
    ]

    found = column_detections(text, columns, frozenset({"payee"}), 1.0)

    assert [d.text for d in found] == ["Alex Sample", "Robin Example"]
    assert all(d.source == DetectionSource.TABLE_COLUMN for d in found)
    assert all(d.entity_type == CUSTOM_ENTITY_TYPE for d in found)


def test_column_detections_never_redacts_the_header() -> None:
    text = "Payee\nPayee Services Co"
    columns = [TableColumn("Payee", ("Payee Services Co",))]

    found = column_detections(text, columns, frozenset({"payee"}), 1.0)

    assert [d.text for d in found] == ["Payee Services Co"]


def test_column_detections_matches_the_value_elsewhere_on_the_page() -> None:
    text = "Alex Sample 100.00\nApproved for Alex Sample."
    columns = [TableColumn("Payee", ("Alex Sample",))]

    found = column_detections(text, columns, frozenset({"payee"}), 1.0)

    assert len(found) == 2


def test_a_wrapped_cell_not_found_whole_is_matched_line_by_line() -> None:
    # The page text broke the cell with a hyphen, so the whole value is absent.
    text = "Sample Hold-\nings Ltd\nAlex Sample"
    columns = [TableColumn("Payee", ("Sample Holdings\nAlex Sample",))]

    found = column_detections(text, columns, frozenset({"payee"}), 1.0)

    assert "Alex Sample" in [d.text for d in found]


def test_nothing_chosen_means_no_detections() -> None:
    columns = [TableColumn("Payee", ("Alex Sample",))]

    assert column_detections("Alex Sample", columns, frozenset(), 1.0) == []
