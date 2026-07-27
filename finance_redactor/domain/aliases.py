"""Name variant generation for master-list matching.

The master list stores one surface form per name (e.g. ``Acme Ltd``), but documents
use many: ``Acme Limited``, ``Acme Ltd.``, ``Smith & Co`` vs ``Smith and Co``. To fold
those onto the curated ID without editing the workbook, this module derives, from one
master-list name, both:

- the set of variant **surface strings** (:func:`aliases`) — used to register extra
  lookup keys in the master map; and
- one **regex source** (:func:`name_pattern`) matching every variant — used by the
  custom recognizer so it detects the variants in the first place.

Both derive from the same suffix / ampersand rules, so the recognizer's matchable set
exactly equals the map's resolvable set.

Framework-free and unit-testable. No middle-initial handling by design: stripping
initials would merge ``Brian O. Thuo`` and ``Brian A. Thuo`` into one pseudonym, which
breaks the per-entity identity guarantee the tool exists to provide.
"""

from __future__ import annotations

import itertools
import re

# Canonical short suffix -> its long-form equivalent(s). Used for both ``aliases`` and
# ``name_pattern`` so the two stay in sync.
SUFFIX_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "ltd": ("limited",),
    "inc": ("incorporated",),
    "corp": ("corporation",),
    "co": ("company",),
}

# Every suffix form (short or long) -> all equivalent forms (short form first). Symmetric
# so a workbook that stores the long form (``Acme Limited``) still generates the short
# alias (``Acme Ltd``) and vice versa. ``llc``/``plc`` have no equivalent, just themselves.
_SUFFIX_TO_FORMS: dict[str, list[str]] = {}
for _short, _longs in SUFFIX_EQUIVALENTS.items():
    _forms = [_short, *_longs]
    for _f in _forms:
        _SUFFIX_TO_FORMS[_f] = _forms
for _f in ("llc", "plc"):
    _SUFFIX_TO_FORMS[_f] = [_f]

# Tokens recognized as org suffixes (lowercased, period stripped) — short and long forms.
SUFFIX_SET: frozenset[str] = frozenset(_SUFFIX_TO_FORMS)


def _dedup(items: list[str]) -> list[str]:
    """Return ``items`` with duplicates removed, preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _suffix_forms(core: str) -> list[str]:
    """Lowercase surface forms for a suffix token, with and without a trailing period.

    ``core`` is the lowercased, period-stripped suffix (e.g. ``ltd``). The trailing-period
    forms matter for spaCy detections that include the period in the entity span.
    """
    forms = _SUFFIX_TO_FORMS.get(core, [core])
    with_periods: list[str] = []
    for form in forms:
        with_periods.append(form)
        with_periods.append(form + ".")
    return _dedup(with_periods)


def _amp_variants(stem: str) -> list[str]:
    """Expand every ``&``/``and`` token in ``stem`` to both forms (full cross-product).

    A name with two ampersand tokens therefore yields all four combinations, matching
    whatever mix the document uses. Substring-safe: only whole ``&``/``and`` tokens are
    swapped (``Thailand`` is untouched).
    """
    tokens = stem.split()
    amp_positions = [
        i
        for i, tok in enumerate(tokens)
        if tok == "&" or tok.rstrip(".").lower() == "and"
    ]
    if not amp_positions:
        return [stem]
    variants: list[str] = [stem]
    for combo in itertools.product(("&", "and"), repeat=len(amp_positions)):
        toks = list(tokens)
        for pos, replacement in zip(amp_positions, combo, strict=True):
            toks[pos] = replacement
        variants.append(" ".join(toks))
    return _dedup(variants)


def aliases(name: str) -> list[str]:
    """Return the surface-form variants of ``name`` (the original always first).

    Variants come from the cross-product of org-suffix equivalent forms (last token only)
    and ``&``/``and`` swaps. The list is deduped and order-preserving; the original name
    leads so callers can treat index 0 as the canonical form.
    """
    name = name.strip()
    if not name:
        return []
    tokens = name.split()
    last = tokens[-1]
    last_core = last.rstrip(".").lower()

    if last_core in SUFFIX_SET and len(tokens) >= 2:
        stem = " ".join(tokens[:-1])
        stem_variants = _amp_variants(stem)
        suffix_forms = _suffix_forms(last_core)
        results = [f"{sv} {sf}".strip() for sv in stem_variants for sf in suffix_forms]
    elif last_core in SUFFIX_SET:
        # Name is a bare suffix token (e.g. "Ltd"); nothing meaningful to expand.
        results = [name]
    else:
        results = _amp_variants(name)

    return _dedup([name, *results])


def name_pattern(name: str) -> str:
    r"""Return a regex source matching every variant of ``name`` (no word-boundary wraps).

    Tokens are joined with ``\\s+`` (whitespace-flexible). The last token, when it is an
    org suffix, becomes an alternation of equivalent forms (``(?:ltd|limited)``);
    ``&``/``and`` tokens become ``(?:and|&)``. The caller wraps this with a leading
    ``\\b`` and a trailing ``(?!\\w)`` — the right side is a non-word lookahead rather
    than ``\\b`` so an optional trailing period (left unconsumed) doesn't break the
    boundary.
    """
    name = name.strip()
    if not name:
        return ""
    tokens = name.split()
    parts: list[str] = []
    for index, tok in enumerate(tokens):
        is_last = index == len(tokens) - 1
        core = tok.rstrip(".").lower()
        if tok == "&" or core == "and":
            parts.append(r"(?:and|&)")
        elif is_last and core in SUFFIX_SET:
            forms = _SUFFIX_TO_FORMS.get(core, [core])
            alts = _dedup([re.escape(form) for form in forms])
            parts.append("(?:" + "|".join(alts) + ")")
        else:
            parts.append(re.escape(tok))
    return r"\s+".join(parts)
