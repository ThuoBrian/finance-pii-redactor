"""Single source of truth for tunable settings.

Replaces the scattered module-level constants in the old ``redactor/config.py``
with one immutable ``Settings`` object that can be constructed with overrides
(useful for tests) and injected from the composition root.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

# The master list lives in a top-level ``data/`` folder next to the package -
# user-owned config, kept separate from the code and out of git. It is now an
# Excel workbook with one sheet per category. (Resolved from this file:
# finance_redactor/config.py -> repo root -> data/.)
_DATA_DIR = Path(__file__).parent.parent / "data"

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
_DEFAULT_AUTO_PREFIXES: Mapping[str, str] = MappingProxyType(
    {"PERSON": "PSN", "ORGANIZATION": "ORG", "EMAIL_ADDRESS": "EML"}
)


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration.

    Defaults reproduce the tool's behavior; detection tuning lives here alongside
    the pseudonymization vocabulary (categories and auto-id prefixes).
    """

    language: str = "en"
    spacy_model: str = "en_core_web_lg"
    supported_entities: tuple[str, ...] = ("PERSON", "ORGANIZATION", "EMAIL_ADDRESS")
    categories: Mapping[str, tuple[str, str]] = _DEFAULT_CATEGORIES
    auto_prefixes: Mapping[str, str] = _DEFAULT_AUTO_PREFIXES
    custom_match_score: float = 0.9
    default_threshold: float = 0.35
    names_dir: Path = field(default=_DATA_DIR)

    @property
    def master_list_file(self) -> Path:
        """Path to the Excel master list (sheets: Vendors, Funders, Staff)."""
        return self.names_dir / "Names List - Organized.xlsx"


DEFAULT_SETTINGS = Settings()
