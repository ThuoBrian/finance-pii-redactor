"""Scoring rules for the detection harness (eval/scoring.py)."""

from __future__ import annotations

from eval.corpus import Gold
from eval.scoring import appears, fold, is_true_positive, score


def test_appears_matches_whole_words_ignoring_case_accents_and_spacing():
    text = fold("Paid to  JOSÉ   Example\nyesterday")
    assert appears("Jose Example", text)
    assert not appears("Jose Exam", text)  # not a whole word
    assert not appears("Example Jose", text)


def test_true_positive_on_shared_word_or_line_break_prefix():
    gold = ["Abena Kevlinya"]
    assert is_true_positive("Abena Kev-", gold)
    assert is_true_positive("ABENA", gold)
    assert not is_true_positive("Invoice 2231", gold)
    assert not is_true_positive("of a", gold)  # short words never count


def _gold(category: str, value: str) -> Gold:
    return Gold("d1", "docx", category, value)


def test_score_counts_leaks_negatives_and_false_positives():
    gold = [
        _gold("master_person", "Alex Sample"),
        _gold("unlisted_person", "Robin Example"),
        _gold("surname_only", "Testperson"),
        _gold("legal_terms", "Force Majeure"),
        _gold("legal_terms", "Governing Law"),
    ]
    output = "Paid STF-1 and Robin Example. Ask Testperson. [001] clause. Governing Law"
    report = score(gold, {"d1": output}, {"d1": ["Alex Sample", "Force Majeure"]})

    summary = report["summary"]
    assert summary["gold"] == 2  # known limits and negatives are not counted
    assert summary["leaked"] == 1
    assert summary["recall"] == 0.5
    assert summary["known_limit_leaked"] == 1
    assert summary["negatives_redacted"] == 1
    assert summary["false_positives"] == 1
    assert summary["precision"] == 0.5
    assert report["recall"]["unlisted_person"]["docx"] == {"total": 1, "leaked": 1}
    assert [g["value"] for g in report["leaked"]] == ["Robin Example", "Testperson"]
    assert report["top_false_positives"] == [("Force Majeure", 1)]


def test_score_handles_no_detections():
    report = score([_gold("master_person", "Alex Sample")], {"d1": "STF-1"}, {"d1": []})
    assert report["summary"]["precision"] is None
    assert report["summary"]["recall"] == 1.0
