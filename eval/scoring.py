"""Score redacted output against gold labels. Pure functions, no I/O.

Two measures:

- **Leaks** (recall): a positive gold value still readable in the redacted
  output leaked. This checks what a reader would actually see, so it also
  catches findings the PDF flow detected but could not locate on the page.
- **False positives** (precision): a detection that overlaps no positive gold
  value in its document. Separately, each negative probe ("Force Majeure")
  that disappeared from the output was wrongly redacted.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from eval.corpus import Gold
from eval.scenarios import KNOWN_LIMITS
from finance_redactor.domain.pseudonyms import fold_diacritics


def fold(text: str) -> str:
    """Accent-fold, casefold and collapse whitespace."""
    return " ".join(fold_diacritics(text).casefold().split())


def appears(value: str, folded_text: str) -> bool:
    """Whether ``value`` occurs in already-folded text as a whole word run."""
    pattern = r"\s+".join(re.escape(word) for word in fold(value).split())
    return re.search(rf"(?<!\w){pattern}(?!\w)", folded_text) is not None


def is_true_positive(detected: str, positives: Iterable[str]) -> bool:
    """Whether a detection shares a word with a positive gold value.

    A word also counts if it starts a gold word, since a PDF line break can
    cut a name in two (``Abena Kev-``). Words under three letters are ignored
    so "a" or "of" never makes a detection count.
    """
    tokens = [t for t in re.findall(r"\w+", fold(detected)) if len(t) >= 3]
    gold_words = {w for value in positives for w in re.findall(r"\w+", fold(value))}
    return any(w.startswith(t) for t in tokens for w in gold_words)


def score(
    gold: list[Gold],
    outputs: Mapping[str, str],
    detections: Mapping[str, list[str]],
) -> dict[str, Any]:
    """Return the report: per-category tables, totals, and the offending values.

    ``outputs`` maps document name to the redacted output's text, and
    ``detections`` maps it to the detected texts.
    """
    folded = {doc: fold(text) for doc, text in outputs.items()}
    recall: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    negatives: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    leaked: list[dict[str, str]] = []
    wrongly_redacted: list[dict[str, str]] = []

    for item in gold:
        still_there = appears(item.value, folded[item.doc])
        if item.negative:
            cell = negatives[item.category][item.file_type]
            cell["total"] += 1
            if not still_there:
                cell["redacted"] += 1
                wrongly_redacted.append(item.to_dict())
        else:
            cell = recall[item.category][item.file_type]
            cell["total"] += 1
            if still_there:
                cell["leaked"] += 1
                leaked.append(item.to_dict())

    positives: dict[str, list[str]] = defaultdict(list)
    file_types: dict[str, str] = {}
    for item in gold:
        file_types[item.doc] = item.file_type
        if not item.negative:
            positives[item.doc].append(item.value)

    precision: dict[str, Counter[str]] = defaultdict(Counter)
    fp_texts: Counter[str] = Counter()
    for doc, texts in detections.items():
        for text in texts:
            if is_true_positive(text, positives[doc]):
                precision[file_types[doc]]["tp"] += 1
            else:
                precision[file_types[doc]]["fp"] += 1
                fp_texts[text] += 1

    counted = [g for g in gold if not g.negative and g.category not in KNOWN_LIMITS]
    counted_leaks = [g for g in leaked if g["category"] not in KNOWN_LIMITS]
    tp = sum(c["tp"] for c in precision.values())
    fp = sum(c["fp"] for c in precision.values())
    return {
        "summary": {
            "gold": len(counted),
            "leaked": len(counted_leaks),
            "recall": _ratio(len(counted) - len(counted_leaks), len(counted)),
            "detections": tp + fp,
            "false_positives": fp,
            "precision": _ratio(tp, tp + fp),
            "negatives_redacted": len(wrongly_redacted),
            "known_limit_leaked": len(leaked) - len(counted_leaks),
        },
        "recall": _plain(recall),
        "negatives": _plain(negatives),
        "precision": _plain(precision),
        "leaked": leaked,
        "wrongly_redacted": wrongly_redacted,
        "top_false_positives": fp_texts.most_common(30),
    }


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _plain(table: Mapping[str, Any]) -> dict[str, Any]:
    """Turn nested defaultdicts/Counters into sorted plain dicts for JSON."""
    return {
        key: _plain(value) if isinstance(value, Mapping) else value
        for key, value in sorted(table.items())
    }
