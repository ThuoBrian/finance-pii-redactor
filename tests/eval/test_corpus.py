"""The synthetic corpus is deterministic and its gold labels are real."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from eval import corpus, extract, scenarios
from eval.scoring import appears, fold


@pytest.fixture(scope="module")
def built() -> corpus.Corpus:
    return corpus.build(seed=7, size=6)


def test_same_seed_gives_same_corpus(built):
    again = corpus.build(seed=7, size=6)
    assert again.gold == built.gold
    assert [d.name for d in again.docs] == [d.name for d in built.docs]


def test_every_gold_value_is_in_its_document(built):
    for doc in built.docs:
        text = fold(extract.text_of(doc.file_type, doc.data))
        for item in built.gold:
            if item.doc == doc.name:
                assert appears(item.value, text), (doc.name, item)


def test_spreads_across_file_types_and_skips_scans_without_ocr(built):
    assert {d.file_type for d in built.docs} == {"xlsx", "docx", "pdf"}
    with_ocr = corpus.build(seed=7, size=4, ocr=True)
    assert "pdf_scanned" in {d.file_type for d in with_ocr.docs}


def test_each_document_covers_every_core_scenario(built):
    for doc in built.docs:
        categories = {g.category for g in built.gold if g.doc == doc.name}
        assert set(scenarios.RECALL) <= categories
        assert set(scenarios.NEGATIVE) <= categories


def test_master_list_has_the_documented_sheets_and_columns(built):
    sheets = pd.read_excel(BytesIO(built.master_list), sheet_name=None)
    assert set(sheets) == {"Staff", "Vendors", "Funders"}
    for df in sheets.values():
        assert list(df.columns)[:3] == ["Category", "Internal ID", "Name"]
