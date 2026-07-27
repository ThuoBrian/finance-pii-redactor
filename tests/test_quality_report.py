"""Tests for the master-list data-quality guards."""

from __future__ import annotations

import pandas as pd

from finance_redactor.domain.quality import SEVERITY_INFO, SEVERITY_WARNING
from finance_redactor.infrastructure.names.master_list_repository import (
    MasterListRepository,
)

_CATEGORIES = {
    "Staff": ("STF", "PERSON"),
    "Vendor": ("VND", "ORGANIZATION"),
    "Funder": ("FND", "ORGANIZATION"),
}
_CATEGORY_SHEETS = {"Staff": "Staff", "Vendor": "Vendors", "Funder": "Funders"}


def _make_excel(path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def _sheet(category, rows):
    """Build a sheet DataFrame from (id, name) tuples; id None -> blank."""
    return pd.DataFrame(
        {
            "Category": [category] * len(rows),
            "Internal ID": [r[0] for r in rows],
            "Name": [r[1] for r in rows],
            "Primary Subsidiary": [""] * len(rows),
            "Country": [""] * len(rows),
        }
    )


def _repo(path, sheets):
    _make_excel(path, sheets)
    return MasterListRepository(path, _CATEGORIES, category_sheets=_CATEGORY_SHEETS)


def _kinds(issues) -> set[str]:
    return {i.kind for i in issues}


def test_clean_workbook_has_no_issues(tmp_path):
    repo = _repo(
        tmp_path / "clean.xlsx",
        {
            "Staff": _sheet("Staff", [(1, "Brian Thuo")]),
            "Vendors": _sheet("Vendor", [(100, "Acme Ltd")]),
            "Funders": _sheet("Funder", [(200, "Gates Foundation")]),
        },
    )
    assert repo.quality_report() == []


def test_cross_category_duplicate_is_warning(tmp_path):
    repo = _repo(
        tmp_path / "cross.xlsx",
        {
            "Staff": _sheet("Staff", [(1, "Acme Corp")]),
            "Vendors": _sheet("Vendor", [(2, "Acme Corp")]),
            "Funders": _sheet("Funder", [(3, "Unique Foundation")]),
        },
    )
    issues = {i.kind: i for i in repo.quality_report()}
    assert "cross_category_duplicate" in issues
    issue = issues["cross_category_duplicate"]
    assert issue.severity == SEVERITY_WARNING
    assert issue.total == 1
    # Names are shown normalized (case-collapsed) by duplicate_names().
    assert any("acme corp" in ex for ex in issue.examples)


def test_conflicting_ids_same_name_different_ids(tmp_path):
    # Same name, same category, two different Internal IDs -> conflict.
    repo = _repo(
        tmp_path / "conflict.xlsx",
        {"Vendors": _sheet("Vendor", [(100, "Acme Ltd"), (200, "Acme Ltd")])},
    )
    issues = {i.kind: i for i in repo.quality_report()}
    assert "conflicting_ids" in issues
    issue = issues["conflicting_ids"]
    assert issue.severity == SEVERITY_WARNING
    assert issue.total == 1
    assert "VND-100" in issue.examples[0]
    assert "VND-200" in issue.examples[0]


def test_blank_ids_are_advisory_info(tmp_path):
    repo = _repo(
        tmp_path / "blank.xlsx",
        {"Staff": _sheet("Staff", [(None, "No Id Person"), (5, "Has Id")])},
    )
    issues = {i.kind: i for i in repo.quality_report()}
    assert "blank_ids" in issues
    issue = issues["blank_ids"]
    assert issue.severity == SEVERITY_INFO  # supported behavior, not an error
    assert issue.total == 1
    assert any("No Id Person" in ex for ex in issue.examples)


def test_duplicate_id_reused_by_different_names(tmp_path):
    # One Internal ID shared by two different names within a category.
    repo = _repo(
        tmp_path / "dupid.xlsx",
        {"Vendors": _sheet("Vendor", [(100, "Acme Ltd"), (100, "Beta Inc")])},
    )
    issues = {i.kind: i for i in repo.quality_report()}
    assert "duplicate_ids" in issues
    issue = issues["duplicate_ids"]
    assert issue.severity == SEVERITY_WARNING
    assert issue.total == 1
    ex = issue.examples[0]
    assert "VND-100" in ex
    assert "Acme Ltd" in ex
    assert "Beta Inc" in ex


def test_exact_duplicate_row_not_flagged(tmp_path):
    # Same name AND same ID is a benign duplicate, not a conflict or reuse.
    repo = _repo(
        tmp_path / "benign.xlsx",
        {"Vendors": _sheet("Vendor", [(100, "Acme Ltd"), (100, "Acme Ltd")])},
    )
    issues = repo.quality_report()
    assert "conflicting_ids" not in _kinds(issues)
    assert "duplicate_ids" not in _kinds(issues)


def test_example_cap_and_remaining_count(tmp_path):
    # Six cross-category duplicates -> 5 examples + "... and 1 more".
    sheets = {}
    names = [f"Dupe{i}" for i in range(6)]
    sheets["Staff"] = _sheet("Staff", [(i, n) for i, n in enumerate(names)])
    sheets["Vendors"] = _sheet("Vendor", [(100 + i, n) for i, n in enumerate(names)])
    sheets["Funders"] = _sheet("Funder", [(1, "Unique Foundation")])
    repo = _repo(tmp_path / "many.xlsx", sheets)

    issue = {i.kind: i for i in repo.quality_report()}["cross_category_duplicate"]
    assert len(issue.examples) == 5
    assert issue.total == 6
