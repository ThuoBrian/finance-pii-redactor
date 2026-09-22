"""Unit tests for the framework-free pseudonymization logic."""

from __future__ import annotations

from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span
from finance_redactor.domain.pseudonyms import (
    MasterEntry,
    Pseudonymizer,
    apply_replacements,
    format_label,
    normalize,
)

_AUTO_PREFIXES = {"PERSON": "PSN", "ORGANIZATION": "ORG"}


def _detection(start: int, end: int, text: str, entity: str = "PERSON") -> PiiDetection:
    return PiiDetection(
        entity_type=entity,
        span=Span(start, end),
        score=0.9,
        text=text,
        source=DetectionSource.MASTER_LIST,
    )


def test_master_hit_returns_curated_id():
    master = {("PERSON", normalize("Jane Doe")): MasterEntry("STF-10010", "Staff")}
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("PERSON", "jane  doe")  # case/space insensitive

    assert assignment.pseudonym == "STF-10010"
    assert assignment.category == "Staff"
    assert assignment.auto is False


def test_unknown_name_gets_stable_auto_id():
    a = Pseudonymizer({}, _AUTO_PREFIXES).assign("PERSON", "Jane Doe")
    b = Pseudonymizer({}, _AUTO_PREFIXES).assign("PERSON", "JANE   doe")

    assert a.auto is True
    assert a.pseudonym.startswith("PSN-AUTO-")
    # Deterministic across instances and insensitive to case/whitespace.
    assert a.pseudonym == b.pseudonym


def test_auto_prefix_follows_entity_type():
    p = Pseudonymizer({}, _AUTO_PREFIXES)
    assert p.assign("ORGANIZATION", "Acme Co").pseudonym.startswith("ORG-AUTO-")


def test_typo_gets_auto_id_plus_a_suggestion_not_a_silent_merge():
    master = {
        ("PERSON", normalize("Michael Sample")): MasterEntry(
            "STF-10010", "Staff", display_name="Michael Sample"
        )
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("PERSON", "Micheal Sample")  # typo: swapped "ae"

    # Never silently resolves to the curated id - still a flagged auto-id.
    assert assignment.auto is True
    assert assignment.pseudonym.startswith("PSN-AUTO-")
    assert assignment.pseudonym != "STF-10010"
    # ...but carries a reviewer hint pointing at the likely intended match.
    assert assignment.suggested_pseudonym == "STF-10010"
    assert assignment.suggested_name == "Michael Sample"
    assert assignment.suggested_score is not None and assignment.suggested_score >= 0.84


def test_no_suggestion_when_nothing_close_enough():
    master = {
        ("PERSON", normalize("Michael Sample")): MasterEntry("STF-10010", "Staff")
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("PERSON", "Completely Different Name")

    assert assignment.auto is True
    assert assignment.suggested_pseudonym is None
    assert assignment.suggested_name is None
    assert assignment.suggested_score is None


def test_suggestion_is_scoped_to_the_same_entity_type():
    # A PERSON name should never be suggested as a fuzzy match for an
    # ORGANIZATION detection, even if the strings are similar.
    master = {("PERSON", normalize("Micheal Corp")): MasterEntry("STF-1", "Staff")}
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("ORGANIZATION", "Micheal Corp")

    assert assignment.suggested_pseudonym is None


def test_repeated_name_is_consistent_and_recorded_once():
    master = {("PERSON", normalize("Jane Doe")): MasterEntry("STF-10010", "Staff")}
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    first = p.assign("PERSON", "Jane Doe")
    second = p.assign("PERSON", "jane doe")

    assert first.pseudonym == second.pseudonym
    assert len(p.crosswalk()) == 1


def test_apply_replacements_handles_multiple_and_overlap():
    text = "Jane Doe paid Northwind Supplies"
    detections = [
        _detection(0, 8, "Jane Doe"),
        _detection(14, 32, "Northwind Supplies", entity="ORGANIZATION"),
        # Overlapping shorter span that should be dropped by dedupe.
        _detection(0, 4, "Jane"),
    ]
    master = {
        ("PERSON", normalize("Jane Doe")): MasterEntry("STF-10010", "Staff"),
        ("ORGANIZATION", normalize("Northwind Supplies")): MasterEntry(
            "VND-10011", "Vendor"
        ),
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    result = apply_replacements(
        text, detections, lambda d: p.assign(d.entity_type, d.text).pseudonym
    )

    assert result == "STF-10010 paid VND-10011"


def test_apply_replacements_preserves_offsets_right_to_left():
    text = "aaa NAME bbb NAME ccc"
    detections = [_detection(4, 8, "NAME"), _detection(13, 17, "NAME")]
    p = Pseudonymizer({}, _AUTO_PREFIXES)

    result = apply_replacements(
        text, detections, lambda d: p.assign(d.entity_type, d.text).pseudonym
    )

    # Both occurrences of the same name collapse to one pseudonym.
    pseudonym = p.assign("PERSON", "NAME").pseudonym
    assert result == f"aaa {pseudonym} bbb {pseudonym} ccc"


# --- Document-local labels ---------------------------------------------------


def test_labels_number_from_first_appearance():
    """Labels are assigned in the order entities are first seen, from [001]."""
    p = Pseudonymizer({}, _AUTO_PREFIXES)

    first = p.assign("PERSON", "Aaa Person")
    second = p.assign("ORGANIZATION", "Bbb Org")

    assert first.label == "[001]"
    assert second.label == "[002]"


def test_repeated_entity_reuses_its_label():
    p = Pseudonymizer({}, _AUTO_PREFIXES)

    first = p.assign("PERSON", "Aaa Person")
    p.assign("PERSON", "Bbb Person")
    again = p.assign("PERSON", "aaa   person")

    assert again.label == first.label == "[001]"


def test_label_widens_rather_than_truncating_past_999():
    """[1000] is correct and sortable-enough; truncating would collide."""
    assert format_label(7) == "[007]"
    assert format_label(999) == "[999]"
    assert format_label(1000) == "[1000]"


def test_crosswalk_is_in_label_order_not_grouped_by_flag():
    """The mapping is a lookup table: row 7 must be findable from [007]."""
    master = {
        ("PERSON", normalize("Curated Person")): MasterEntry(
            "STF-10010", "Staff", internal_id="10010"
        )
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    p.assign("PERSON", "Unknown One")  # auto
    p.assign("PERSON", "Curated Person")  # curated
    p.assign("PERSON", "Unknown Two")  # auto

    assert [a.label for a in p.crosswalk()] == ["[001]", "[002]", "[003]"]


# --- Internal IDs and the name-only fallback ---------------------------------


def test_curated_hit_carries_the_raw_internal_id():
    """The mapping file needs 10010, not just the string "STF-10010"."""
    master = {
        ("PERSON", normalize("Curated Person")): MasterEntry(
            "STF-10010", "Staff", internal_id="10010"
        )
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("PERSON", "Curated Person")

    assert assignment.internal_id == "10010"
    assert assignment.auto is False


def test_orphan_has_no_internal_id():
    assignment = Pseudonymizer({}, _AUTO_PREFIXES).assign("PERSON", "Unknown Person")

    assert assignment.internal_id is None
    assert assignment.auto is True
    assert assignment.ambiguous is False


def test_typed_custom_word_resolves_across_entity_types():
    """A CUSTOM detection can never match the map's (PERSON, name) key.

    This is the gap that made the two-hop scheme impossible for PDFs: typed
    words are the only way to redact a name there, and without a name-only
    fallback they could never carry a curated Internal ID.
    """
    master = {
        ("ORGANIZATION", normalize("Care Organisation")): MasterEntry(
            "VND-17728", "Vendor", internal_id="17728"
        )
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("CUSTOM", "Care Organisation")

    assert assignment.internal_id == "17728"
    assert assignment.category == "Vendor"
    assert assignment.auto is False


def test_typed_custom_word_resolves_across_accents():
    """custom_words matches accent-insensitively, so the lookup must too.

    The detection reports the document's own accented spelling, so without
    folding here a typed unaccented word would match in the document and then
    silently fail to resolve against an unaccented master row.
    """
    master = {
        ("PERSON", normalize("Jose Garcia")): MasterEntry(
            "STF-10020", "Staff", internal_id="10020"
        )
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("CUSTOM", "José García")

    assert assignment.internal_id == "10020"


def test_person_never_widens_to_an_organization_row():
    """A typed entity type that misses is a genuine miss.

    Widening would write a *wrong* Internal ID, which under a names-free
    mapping is undetectable downstream. An orphan is merely inconvenient.
    """
    master = {
        ("ORGANIZATION", normalize("Ambiguous Name")): MasterEntry(
            "VND-17728", "Vendor", internal_id="17728"
        )
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("PERSON", "Ambiguous Name")

    assert assignment.auto is True
    assert assignment.internal_id is None


def test_name_in_two_categories_refuses_rather_than_guessing():
    """Conflicting curated rows must not resolve to a coin-flip ID."""
    master = {
        ("ORGANIZATION", normalize("Shared Name")): MasterEntry(
            "VND-17728", "Vendor", internal_id="17728"
        ),
        ("PERSON", normalize("Shared Name")): MasterEntry(
            "STF-10030", "Staff", internal_id="10030"
        ),
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("CUSTOM", "Shared Name")

    assert assignment.internal_id is None
    assert assignment.ambiguous is True
    assert assignment.auto is True
    # Still redacted - refusing to resolve must never mean refusing to redact.
    assert "-AUTO-" in assignment.pseudonym


def test_same_name_same_id_in_both_categories_is_not_ambiguous():
    """Two rows agreeing on the ID is not a conflict."""
    entry = MasterEntry("VND-17728", "Vendor", internal_id="17728")
    master = {
        ("ORGANIZATION", normalize("Shared Name")): entry,
        ("URL", normalize("Shared Name")): entry,
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("CUSTOM", "Shared Name")

    assert assignment.internal_id == "17728"
    assert assignment.ambiguous is False


def test_typed_word_typo_gets_a_hint_now_that_pdf_sees_the_master_list():
    """Previously impossible: _candidates_by_type["CUSTOM"] is always empty."""
    master = {
        ("ORGANIZATION", normalize("Care Organisation")): MasterEntry(
            "VND-17728", "Vendor", display_name="Care Organisation", internal_id="17728"
        )
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("CUSTOM", "Care Organistaion")  # transposed "ai"

    assert assignment.auto is True
    assert assignment.suggested_name == "Care Organisation"
    assert assignment.suggested_pseudonym == "VND-17728"
