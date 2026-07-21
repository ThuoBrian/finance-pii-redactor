"""Unit tests for the Excel master-list repository."""

from __future__ import annotations

import pandas as pd

from finance_redactor.domain.pseudonyms import normalize
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


def _make_excel(path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def _repo(tmp_path, category_sheets=None):
    sheets = {
        "Staff": pd.DataFrame(
            {
                "Category": ["Staff", "Staff", "Staff"],
                "Internal ID": [91345, None, 99],
                "Name": ["Brian Thuo", "No Id Person", ""],
                "Primary Subsidiary": ["IPA-Kenya", "", ""],
                "Country": ["Kenya", "", ""],
            }
        ),
        "Vendors": pd.DataFrame(
            {
                "Category": ["Vendor"],
                "Internal ID": [1045],
                "Name": ["Safaricom LTD"],
                "Primary Subsidiary": ["IPA-Kenya"],
                "Country": ["Kenya"],
            }
        ),
        "Funders": pd.DataFrame(
            {
                "Category": ["Funder", "Mystery"],
                "Internal ID": [7745, 5],
                "Name": ["Gates Foundation", "Unknown Category"],
                "Primary Subsidiary": ["", ""],
                "Country": ["", ""],
            }
        ),
    }
    path = tmp_path / "master_list.xlsx"
    _make_excel(path, sheets)
    return MasterListRepository(path, _CATEGORIES, category_sheets=category_sheets)


def test_missing_file_yields_empty(tmp_path):
    repo = MasterListRepository(tmp_path / "nope.xlsx", _CATEGORIES)
    assert repo.rows() == []
    assert repo.master_map() == {}
    assert repo.names_by_entity() == {}


def test_names_grouped_by_entity_includes_blank_id(tmp_path):
    grouped = _repo(tmp_path, _CATEGORY_SHEETS).names_by_entity()
    assert grouped["PERSON"] == ["Brian Thuo", "No Id Person"]
    assert grouped["ORGANIZATION"] == ["Safaricom LTD", "Gates Foundation"]


def test_master_map_only_includes_curated_ids(tmp_path):
    mapping = _repo(tmp_path, _CATEGORY_SHEETS).master_map()
    assert mapping[("PERSON", normalize("Brian Thuo"))].pseudonym == "STF-91345"
    assert mapping[("ORGANIZATION", normalize("Gates Foundation"))].pseudonym == (
        "FND-7745"
    )
    # Blank-id row is detectable but absent from the curated map.
    assert ("PERSON", normalize("No Id Person")) not in mapping


def test_unknown_category_and_blank_name_are_skipped(tmp_path):
    rows = _repo(tmp_path, _CATEGORY_SHEETS).rows()
    names = {r.name for r in rows}
    assert "Unknown Category" not in names  # unknown category dropped
    assert "" not in names  # blank name dropped


def test_counts_by_category(tmp_path):
    counts = _repo(tmp_path, _CATEGORY_SHEETS).counts_by_category()
    assert counts == {"Staff": 2, "Vendor": 1, "Funder": 1}


def test_duplicate_names_detected(tmp_path):
    sheets = {
        "Staff": pd.DataFrame(
            {
                "Category": ["Staff"],
                "Internal ID": [1],
                "Name": ["Acme Corp"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
        "Vendors": pd.DataFrame(
            {
                "Category": ["Vendor"],
                "Internal ID": [2],
                "Name": ["Acme Corp"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
        "Funders": pd.DataFrame(
            {
                "Category": ["Funder"],
                "Internal ID": [3],
                "Name": ["Unique Foundation"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
    }
    path = tmp_path / "duplicates.xlsx"
    _make_excel(path, sheets)
    repo = MasterListRepository(path, _CATEGORIES, category_sheets=_CATEGORY_SHEETS)

    duplicates = repo.duplicate_names()
    assert "acme corp" in duplicates
    assert duplicates["acme corp"] == ["Staff", "Vendor"]
    assert "unique foundation" not in duplicates


def test_category_sheets_mapping_selects_correct_sheets(tmp_path):
    sheets = {
        "People": pd.DataFrame(
            {
                "Category": ["Staff"],
                "Internal ID": [1],
                "Name": ["Jane Doe"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
        "Suppliers": pd.DataFrame(
            {
                "Category": ["Vendor"],
                "Internal ID": [2],
                "Name": ["Acme Supplies"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
        "Staff": pd.DataFrame(
            {
                "Category": ["Staff"],
                "Internal ID": [99],
                "Name": ["Ignored Sheet"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        ),
    }
    path = tmp_path / "remapped.xlsx"
    _make_excel(path, sheets)
    custom_sheets = {
        "Staff": "People",
        "Vendor": "Suppliers",
        "Funder": "Funders",
    }
    repo = MasterListRepository(path, _CATEGORIES, category_sheets=custom_sheets)

    names = {r.name for r in repo.rows()}
    assert names == {"Jane Doe", "Acme Supplies"}
    assert "Ignored Sheet" not in names


def test_rows_are_reloaded_when_file_changes(tmp_path):
    path = tmp_path / "changing.xlsx"
    sheets = {
        "Staff": pd.DataFrame(
            {
                "Category": ["Staff"],
                "Internal ID": [1],
                "Name": ["First"],
                "Primary Subsidiary": [""],
                "Country": [""],
            }
        )
    }
    _make_excel(path, sheets)
    repo = MasterListRepository(path, _CATEGORIES)
    assert [r.name for r in repo.rows()] == ["First"]

    sheets["Staff"] = pd.DataFrame(
        {
            "Category": ["Staff"],
            "Internal ID": [2],
            "Name": ["Second"],
            "Primary Subsidiary": [""],
            "Country": [""],
        }
    )
    _make_excel(path, sheets)
    assert [r.name for r in repo.rows()] == ["Second"]
