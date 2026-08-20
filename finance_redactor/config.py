"""Single source of truth for tunable settings.

Replaces the scattered module-level constants in the old ``redactor/config.py``
with one immutable ``Settings`` object that can be constructed with overrides
(useful for tests) and injected from the composition root.
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType


def _local_settings_file() -> Path:
    """Path to a small per-user settings file this app itself writes.

    Lives in the user's home directory (survives code updates/reinstalls,
    unlike anything inside the repo's own folder) rather than the repo,
    since it's a machine-local runtime preference, not project config.
    Written by the in-app "Set up shared master list" dialog (see
    finance_redactor/presentation/master_list_setup.py), which exists
    specifically so a shared Box folder location can be picked from the UI
    instead of an OS environment variable that needs a fresh terminal/process
    to take effect (see docs/GOTCHA.md's "0 names" entry). Resolved fresh on
    every call (not cached at import time) so tests can monkeypatch
    ``Path.home``.
    """
    return Path.home() / ".finance_pii_redactor" / "settings.json"


def read_persisted_master_list_dir() -> Path | None:
    """Return the master-list folder saved via the in-app setup dialog, if any."""
    try:
        raw = _local_settings_file().read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    value = data.get("master_list_dir") if isinstance(data, dict) else None
    return Path(value) if value else None


def save_master_list_dir(path: Path) -> None:
    """Persist ``path`` as the master-list folder for all future launches.

    Takes precedence over ``FPR_MASTER_LIST_DIR`` (see ``_resolve_data_dir``)
    and applies on the very next read - no environment variable, registry
    change, or app restart required.
    """
    settings_file = _local_settings_file()
    data: dict[str, object] = {}
    try:
        loaded = json.loads(settings_file.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except (FileNotFoundError, OSError, ValueError):
        pass
    data["master_list_dir"] = str(path)
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _resolve_data_dir() -> Path:
    """Resolve the folder the master-list workbook is read from.

    Defaults to a top-level ``data/`` folder next to the package - user-owned
    config, kept separate from the code and out of git. (Resolved from this
    file: finance_redactor/config.py -> repo root -> data/.)

    Checked in order:

    1. The folder saved via the in-app "Set up shared master list" dialog
       (``read_persisted_master_list_dir``) - wins over the environment
       variable below once set, since it's the easier mechanism for a user to
       manage and applies immediately rather than needing a restart.
    2. The ``FPR_MASTER_LIST_DIR`` environment variable, so a team can instead
       point every teammate's install at one shared, access-controlled
       location (e.g. a permissioned SharePoint/network-drive folder) instead
       of each person maintaining an independent local copy - see
       ``data/README.md`` and ``docs/GOTCHA.md``.
    3. The local ``data/`` folder next to the package.

    The master list is Confidential (real names), so a shared location from
    either mechanism must itself be access-controlled; this only changes
    *where* the file is read from, never how it's handled.
    """
    persisted = read_persisted_master_list_dir()
    if persisted:
        return persisted
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
# Only add entity types here that identify a person/organization, or - like
# "CUSTOM" - a deliberate ad-hoc redaction target the user typed into the
# PDF/Word flows' "words to redact" box (see domain/custom_words.py). Do NOT
# add non-name entity types (e.g. Presidio's "DATE_TIME") to this map or to
# `supported_entities` below: dates/times aren't the PII this tool exists to
# protect, and pseudonymizing them (e.g. turning "Jan-26" into a fake ID) is
# noise, not redaction. Adding one carelessly is also a silent risk - any
# entity type missing from this map falls back to `entity_type[:3].upper()` in
# `Pseudonymizer._auto_pseudonym` (domain/pseudonyms.py) instead of raising an
# error, so "DATE_TIME" would quietly mint "DAT-AUTO-<hash>" ids rather than
# failing loudly. ("CUSTOM"[:3].upper() would itself produce "CUS", not "CST" -
# it's listed explicitly below rather than relying on that fallback.)
_DEFAULT_AUTO_PREFIXES: Mapping[str, str] = MappingProxyType(
    {"PERSON": "PSN", "ORGANIZATION": "ORG", "EMAIL_ADDRESS": "EML", "CUSTOM": "CST"}
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
    # Confidence shown for an ad-hoc "words to redact" match (domain/custom_words.py) -
    # an exact, user-typed term is maximal confidence, unlike a spaCy model guess.
    custom_words_score: float = 1.0
    names_dir: Path = field(default=_DATA_DIR)

    @property
    def master_list_file(self) -> Path:
        """Path to the Excel master list (sheets: Vendors, Funders, Staff)."""
        return self.names_dir / "Names List - Organized.xlsx"


DEFAULT_SETTINGS = Settings()


def current_settings() -> Settings:
    """Return ``Settings`` with ``names_dir`` re-resolved fresh, not cached.

    ``DEFAULT_SETTINGS.names_dir`` is fixed once at import time. Call this
    instead anywhere the master-list folder might have changed since then -
    namely ``app.py``'s ``_main()``, which Streamlit re-executes on every
    interaction (the module itself is only imported once per process, so
    ``DEFAULT_SETTINGS`` alone would never notice a change). Re-resolving
    here is what allows a folder saved via the in-app "Set up shared master
    list" dialog to take effect on the very next rerun, with no app restart.
    """
    return dataclasses.replace(DEFAULT_SETTINGS, names_dir=_resolve_data_dir())
