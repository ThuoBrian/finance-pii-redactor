"""Single source of truth for tunable settings.

Replaces the scattered module-level constants in the old ``redactor/config.py``
with one immutable ``Settings`` object that can be constructed with overrides
(useful for tests) and injected from the composition root.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType


def _resolve_data_dir() -> Path:
    """Resolve the folder the master-list workbook is read from.

    Defaults to a top-level ``data/`` folder next to the package - user-owned
    config, kept separate from the code and out of git. (Resolved from this
    file: finance_redactor/config.py -> repo root -> data/.)

    Honors the ``FPR_MASTER_LIST_DIR`` environment variable when set, so a
    team can point every teammate's install at one shared, access-controlled
    location (e.g. a permissioned SharePoint/network-drive folder) instead of
    each person maintaining an independent local copy - see
    ``data/README.md`` and ``docs/GOTCHA.md``. The master list is Confidential
    (real names), so that shared location must itself be access-controlled;
    this only changes *where* the file is read from, never how it's handled.
    """
    override = os.environ.get("FPR_MASTER_LIST_DIR")
    if override:
        return Path(override)
    return Path(__file__).parent.parent / "data"


# The master list lives in a top-level ``data/`` folder next to the package by
# default. It is now an Excel workbook with one sheet per category.
_DATA_DIR = _resolve_data_dir()

# Maps a master-list ``category`` to its pseudonym prefix and the entity type the
# detector uses for it. Several categories may share one entity type (Vendor and
# Funder are both ORGANIZATION) but keep distinct prefixes.
_DEFAULT_CATEGORIES: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "Staff": ("STF", "PERSON"),
        "Vendor": ("VND", "ORGANIZATION"),
        "Funder": ("FND", "ORGANIZATION"),
    }
)

# Prefix used when a detected name is not in the master list and an auto/placeholder
# pseudonym must be generated (keyed by entity type).
#
# Only add entity types here that identify a person or organization. Do NOT add
# non-name entity types (e.g. Presidio's "DATE_TIME") to this map or to
# `supported_entities` below: dates/times aren't the PII this tool exists to
# protect, and pseudonymizing them (e.g. turning "Jan-26" into a fake ID) is
# noise, not redaction. Adding one carelessly is also a silent risk - any
# entity type missing from this map falls back to `entity_type[:3].upper()` in
# `Pseudonymizer._auto_pseudonym` (domain/pseudonyms.py) instead of raising an
# error, so "DATE_TIME" would quietly mint "DAT-AUTO-<hash>" ids rather than
# failing loudly.
_DEFAULT_AUTO_PREFIXES: Mapping[str, str] = MappingProxyType(
    {"PERSON": "PSN", "ORGANIZATION": "ORG", "EMAIL_ADDRESS": "EML"}
)

# Maps a master-list ``category`` to the Excel sheet name that contains it.
_DEFAULT_CATEGORY_SHEETS: Mapping[str, str] = MappingProxyType(
    {
        "Staff": "Staff",
        "Vendor": "Vendors",
        "Funder": "Funders",
    }
)


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration.

    Defaults reproduce the tool's behavior; detection tuning lives here alongside
    the pseudonymization vocabulary (categories and auto-id prefixes).
    """

    language: str = "en"
    spacy_model: str = "en_core_web_lg"
    # Name/organization/email entity types only - see the note on
    # `_DEFAULT_AUTO_PREFIXES` above for why non-name types (e.g. DATE_TIME)
    # must never be added here.
    supported_entities: tuple[str, ...] = ("PERSON", "ORGANIZATION", "EMAIL_ADDRESS")
    categories: Mapping[str, tuple[str, str]] = _DEFAULT_CATEGORIES
    category_sheets: Mapping[str, str] = _DEFAULT_CATEGORY_SHEETS
    auto_prefixes: Mapping[str, str] = _DEFAULT_AUTO_PREFIXES
    custom_match_score: float = 0.9
    default_threshold: float = 0.35
    fuzzy_match_threshold: float = 0.84
    names_dir: Path = field(default=_DATA_DIR)

    @property
    def master_list_file(self) -> Path:
        """Path to the Excel master list (sheets: Vendors, Funders, Staff)."""
        return self.names_dir / "Names List - Organized.xlsx"


DEFAULT_SETTINGS = Settings()
