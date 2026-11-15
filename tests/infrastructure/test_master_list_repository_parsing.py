"""Excel-specific tests for the master-list repository.

Covers parsing details that do not fit in the basic repository contract tests:
legacy suffix stripping, float-to-string ID conversion, and multi-sheet loading.
"""

from __future__ import annotations

import pandas as pd
import pytest

from finance_redactor.infrastructure.names.master_list_repository import (
    MasterListRepository,
)

_CATEGORIES = {
    "Staff": ("STF", "PERSON"),
    "Vendor": ("VND", "ORGANIZATION"),
    "Funder": ("FND", "ORGANIZATION"),
}

_CATEGORY_SHEETS = {
    "Staff": "Staff",
    "Vendor": "Vendors",
    "Funder": "Funders",
}


def _repo_with_sheets(tmp_path, sheets: dict[str, pd.DataFrame]):
    path = tmp_path / "master.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return MasterListRepository(path, _CATEGORIES, category_sheets=_CATEGORY_SHEETS)


def test_legacy_staff_suffix_is_stripped(tmp_path):
    sheets = {
        "Staff": pd.DataFrame(
            {
                "Category": ["Staff", "Staff", "Staff"],
                "Internal ID": [10001, 10002, 10003],
                "Name": [
                    "Jane Doe - 10001",
                    "  Mary   Testcase - 10002  ",
                    "Peter Sample - 10003",
                ],
                "Primary Subsidiary": ["", "", ""],
                "Country": ["", "", ""],
            }
        )
    }
    repo = _repo_with_sheets(tmp_path, sheets)
    rows = repo.rows()

    assert [r.name for r in rows] == [
        "Jane Doe",
        "Mary Testcase",
        "Peter Sample",
    ]
    assert [r.pseudonym for r in rows] == [
        "STF-10001",
        "STF-10002",
        "STF-10003",
    ]


def test_numeric_internal_id_without_decimal_point(tmp_path):
    sheets = {
        "Vendors": pd.DataFrame(
            {
                "Category": ["Vendor"],
                "Internal ID": [10004.0],  # pandas may read numeric IDs as float
                "Name": ["Northwind Traders Ltd"],
                "Primary Subsidiary": ["IPA-Testland"],
                "Country": ["Testland"],
            }
        )
    }
    repo = _repo_with_sheets(tmp_path, sheets)
    row = repo.rows()[0]

    assert row.pseudonym == "VND-10004"


def test_blank_internal_id_yields_none_pseudonym(tmp_path):
    sheets = {
        "Funders": pd.DataFrame(
            {
                "Category": ["Funder"],
                "Internal ID": [None],
                "Name": ["Placeholder Foundation"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        )
    }
    repo = _repo_with_sheets(tmp_path, sheets)
    row = repo.rows()[0]

    assert row.pseudonym is None
    assert repo.master_map() == {}


def test_all_three_sheets_loaded(tmp_path):
    sheets = {
        "Vendors": pd.DataFrame(
            {
                "Category": ["Vendor"],
                "Internal ID": [1],
                "Name": ["Acme Supplies"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
        "Funders": pd.DataFrame(
            {
                "Category": ["Funder"],
                "Internal ID": [2],
                "Name": ["Acme Foundation"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
        "Staff": pd.DataFrame(
            {
                "Category": ["Staff"],
                "Internal ID": [3],
                "Name": ["Jane Doe"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
    }
    repo = _repo_with_sheets(tmp_path, sheets)

    assert repo.counts_by_category() == {
        "Vendor": 1,
        "Funder": 1,
        "Staff": 1,
    }
    names = repo.names_by_entity()
    assert names["PERSON"] == ["Jane Doe"]
    assert set(names["ORGANIZATION"]) == {"Acme Supplies", "Acme Foundation"}


@pytest.mark.parametrize(
    ("raw_name", "expected", "short"),
    [
        ("Jean-Paul Testname", "Jean-Paul Testname", None),  # no spaced dash
        ("Jane Doe - 10001", "Jane Doe", None),  # sanctioned legacy ID suffix
        # Anything else after " - " is part of the name: kept whole, and the
        # head is matched too (it used to be all that was kept).
        ("Alice - Bob", "Alice - Bob", "Alice"),
        ("Acme - Kenya", "Acme - Kenya", "Acme"),
        ("Acme - Unit 2", "Acme - Unit 2", "Acme"),  # digits, but not only digits
    ],
)
def test_name_cleaning_edge_cases(tmp_path, raw_name, expected, short):
    sheets = {
        "Staff": pd.DataFrame(
            {
                "Category": ["Staff"],
                "Internal ID": [1],
                "Name": [raw_name],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        )
    }
    repo = _repo_with_sheets(tmp_path, sheets)
    row = repo.rows()[0]
    assert (row.name, row.short_name) == (expected, short)


def _vendors(tmp_path, names: list[str], ids: list[int]):
    sheets = {
        "Vendors": pd.DataFrame(
            {"Category": ["Vendor"] * len(names), "Internal ID": ids, "Name": names}
        )
    }
    return _repo_with_sheets(tmp_path, sheets)


def test_dashed_name_matches_full_and_short_form(tmp_path):
    repo = _vendors(tmp_path, ["Acme - Kenya"], [7])

    assert repo.names_by_entity()["ORGANIZATION"] == ["Acme - Kenya", "Acme"]
    mapping = repo.master_map()
    assert mapping[("ORGANIZATION", "acme - kenya")].pseudonym == "VND-7"
    assert mapping[("ORGANIZATION", "acme")].pseudonym == "VND-7"
    issue = {i.kind: i for i in repo.quality_report()}["dash_in_name"]
    assert issue.total == 1
    assert issue.examples == ["`Acme - Kenya` also matches `Acme` (Vendor)"]


def test_shared_short_form_with_different_ids_is_not_resolved(tmp_path):
    repo = _vendors(tmp_path, ["Acme - Kenya", "Acme - Uganda"], [7, 8])

    mapping = repo.master_map()
    assert mapping[("ORGANIZATION", "acme - kenya")].pseudonym == "VND-7"
    assert mapping[("ORGANIZATION", "acme - uganda")].pseudonym == "VND-8"
    # Still detected, but left to a flagged auto-id rather than a guess.
    assert "Acme" in repo.names_by_entity()["ORGANIZATION"]
    assert ("ORGANIZATION", "acme") not in mapping
    # Kept whole, the two rows no longer collapse into a false ID conflict.
    assert "conflicting_ids" not in {i.kind for i in repo.quality_report()}


def test_short_form_never_shadows_a_row_of_that_name(tmp_path):
    repo = _vendors(tmp_path, ["Acme - Kenya", "Acme"], [7, 9])

    assert repo.master_map()[("ORGANIZATION", "acme")].pseudonym == "VND-9"
