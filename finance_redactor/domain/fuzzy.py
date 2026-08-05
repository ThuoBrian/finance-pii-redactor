"""Typo-tolerant *suggestion* fallback for names that miss the master list.

Deliberately advisory only, never authoritative: this never changes which
pseudonym gets assigned. ``aliases.py`` already explains why the tool avoids
normalizing away real differences (middle initials, in that case) — the same
risk applies here, worse. Two distinct real people/organizations can be one
edit apart (``Kevin Otieno`` vs. ``Kelvin Otieno``), so auto-merging on
similarity would silently attach one person's history to another's ID, which
is worse than leaving an auto-generated placeholder for a human to resolve.

Instead, when a name doesn't match anything in the master list (exact or
alias), :func:`closest_match` finds the nearest curated name, if any, so the
crosswalk can show it as a reviewer hint (see ``Assignment.suggested_*`` in
``pseudonyms.py``). A human then decides whether to fix the source document or
add the name to the master list — the pseudonym itself is untouched.
"""

from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher

# Skip candidates whose length differs too much to plausibly be a typo of the
# target. This keeps the scan cheap even against a master list with tens of
# thousands of names, without needing a fuzzy-matching library dependency.
_MAX_LENGTH_DELTA = 3


def closest_match(
    normalized_name: str, candidates: Iterable[str], threshold: float
) -> tuple[str, float] | None:
    """Return the closest ``candidates`` entry to ``normalized_name``, if close enough.

    Both sides are expected to already be normalized (see
    :func:`finance_redactor.domain.pseudonyms.normalize`) so casing/whitespace
    differences don't masquerade as similarity. Returns ``None`` when no
    candidate's similarity ratio (``difflib.SequenceMatcher.ratio``, 0-1) reaches
    ``threshold``, including when ``candidates`` is empty.
    """
    best_candidate: str | None = None
    best_score = 0.0
    for candidate in candidates:
        if abs(len(candidate) - len(normalized_name)) > _MAX_LENGTH_DELTA:
            continue
        score = SequenceMatcher(None, normalized_name, candidate).ratio()
        if score > best_score:
            best_score = score
            best_candidate = candidate
    if best_candidate is not None and best_score >= threshold:
        return best_candidate, best_score
    return None
