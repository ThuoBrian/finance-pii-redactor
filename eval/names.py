"""Invented people and organizations for the synthetic corpus.

Surnames are built from syllables by a seeded RNG, and organizations from
made-up word pairs, so no value here is taken from a real record. Given
names on their own are common words, not personal data.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

GIVEN_NAMES = (
    "Amani", "Wanjiru", "Kofi", "Nadia", "Tendai", "Lucia", "Ravi", "Imani",
    "Thabo", "Ayesha", "Mateo", "Zawadi", "Kwame", "Priya", "Baraka", "Selam",
    "Juma", "Esther", "Halima", "Diego", "Fatou", "Nkechi", "Samir", "Grace",
    "Tomas", "Akosua", "Farah", "Yusuf", "Mercy", "Ivana", "Otieno", "Rehema",
    "Kiran", "Abena", "Musa", "Leila", "Chidi", "Noor", "Pedro", "Sipho",
)  # fmt: skip

_SYLLABLES = (
    "ka", "ri", "mbo", "we", "lu", "ndi", "to", "sa", "ke", "no", "ya", "be",
    "ru", "ta", "mi", "go", "zu", "pe", "ha", "dra", "ven", "sho", "lin", "mar",
)  # fmt: skip

_ORG_FIRST = (
    "Kestrel", "Tamarind", "Bluefin", "Harrowmere", "Juniper", "Copperleaf",
    "Sablecrest", "Marigold", "Ironbark", "Lakeshore", "Baobab", "Silverline",
    "Redwater", "Highveld", "Cedarbrook", "Northgate", "Amberfield", "Quillon",
    "Duneview", "Pelican", "Stonereach", "Willowmere", "Brightwater", "Granitepeak",
)  # fmt: skip

_ORG_SECOND = (
    "Logistics", "Consulting", "Supplies", "Partners", "Traders", "Holdings",
    "Agencies", "Systems", "Printers", "Catering", "Motors", "Analytics",
)  # fmt: skip

# Suffixes the master list may store; ``alias_of`` swaps them for an
# equivalent form the matcher should still resolve.
_SUFFIXES = ("Ltd", "Limited", "Inc", "Corp")
_ALIAS = {
    "Ltd": "Limited",
    "Limited": "Ltd",
    "Inc": "Incorporated",
    "Corp": "Corporation",
}

_FUNDER_WORDS = ("Foundation", "Trust", "Fund")


@dataclass(frozen=True)
class Person:
    """An invented person."""

    given: str
    surname: str

    @property
    def full(self) -> str:
        """Return ``Given Surname``."""
        return f"{self.given} {self.surname}"


def surname(rng: random.Random) -> str:
    """Return an invented two- or three-syllable surname."""
    parts = rng.choices(_SYLLABLES, k=rng.choice((2, 3)))
    return "".join(parts).capitalize()


def person(rng: random.Random) -> Person:
    """Return an invented person."""
    return Person(rng.choice(GIVEN_NAMES), surname(rng))


def vendor(rng: random.Random) -> str:
    """Return an invented vendor, usually with a legal suffix."""
    first, second = rng.choice(_ORG_FIRST), rng.choice(_ORG_SECOND)
    if rng.random() < 0.2:
        return f"{first} & {second}"
    return f"{first} {second} {rng.choice(_SUFFIXES)}"


def funder(rng: random.Random) -> str:
    """Return an invented funder."""
    return f"{rng.choice(_ORG_FIRST)} {rng.choice(_FUNDER_WORDS)}"


def alias_of(org: str) -> str | None:
    """Return an equivalent surface form the master list should match, if any."""
    if " & " in org:
        return org.replace(" & ", " and ")
    head, _, last = org.rpartition(" ")
    return f"{head} {_ALIAS[last]}" if last in _ALIAS else None
