"""Unit tests for the CSV master-list repository."""

from __future__ import annotations

from finance_redactor.domain.pseudonyms import normalize
from finance_redactor.infrastructure.names.master_list_repository import (
    MasterListRepository,
)

_CATEGORIES = {
    "Staff": ("STF", "PERSON"),
    "Vendor": ("VND", "ORGANIZATION"),
    "Funder": ("FND", "ORGANIZATION"),
}

_CSV = """# comment line is ignored
category,name,id
Staff,Brian Thuo,91345
Vendor,Safaricom LTD,1045
Funder,Gates Foundation,7745

Staff,No Id Person,
Mystery,Unknown Category,5
Staff,,99
"""


def _repo(tmp_path):
    path = tmp_path / "master_list.csv"
    path.write_text(_CSV, encoding="utf-8")
    return MasterListRepository(path, _CATEGORIES)


def test_missing_file_yields_empty(tmp_path):
    repo = MasterListRepository(tmp_path / "nope.csv", _CATEGORIES)
    assert repo.rows() == []
    assert repo.master_map() == {}
    assert repo.names_by_entity() == {}


def test_names_grouped_by_entity_includes_blank_id(tmp_path):
    grouped = _repo(tmp_path).names_by_entity()
    assert grouped["PERSON"] == ["Brian Thuo", "No Id Person"]
    assert set(grouped["ORGANIZATION"]) == {"Safaricom LTD", "Gates Foundation"}


def test_master_map_only_includes_curated_ids(tmp_path):
    mapping = _repo(tmp_path).master_map()
    assert mapping[("PERSON", normalize("Brian Thuo"))].pseudonym == "STF-91345"
    assert mapping[("ORGANIZATION", normalize("Gates Foundation"))].pseudonym == (
        "FND-7745"
    )
    # Blank-id row is detectable but absent from the curated map.
    assert ("PERSON", normalize("No Id Person")) not in mapping


def test_unknown_category_and_blank_name_are_skipped(tmp_path):
    rows = _repo(tmp_path).rows()
    names = {r.name for r in rows}
    assert "Unknown Category" not in names  # unknown category dropped
    assert "" not in names  # blank name dropped


def test_counts_by_category(tmp_path):
    counts = _repo(tmp_path).counts_by_category()
    assert counts == {"Staff": 2, "Vendor": 1, "Funder": 1}
