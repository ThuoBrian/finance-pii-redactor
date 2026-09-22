"""Guard: no real staff names, organizations, or internal IDs in the repo.

Real master-list values were committed to this public repository and removed
on 2026-09-22. This test stops them coming back.

The forbidden values are stored as truncated SHA-256 digests of their
normalized form, never as plaintext, so this file cannot itself reintroduce
what it guards against. The trade-off is that a failure reports *where* a
match was found, not *what* it was - look at the reported file and line.

If this fails: replace the offending value with synthetic test data, per the
policy in docs/TESTING.md.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".bat", ".sh", ".ps1"}

# The maintainer's own name is legitimate as the byline in these two files.
# It is forbidden everywhere else, where it would be test or example data.
_BYLINE_FILES = {"README.md", "CONTRIBUTING.md"}

_FORBIDDEN = frozenset(
    {
        "20636c6e2f122120",
        "cc44765bfdc19203",
        "3e43f3063441d1c9",
        "0bc0da658a8e1358",
        "b52ebb4f632e5268",
        "33c8d3444f8929c4",
        "3ebffcf1a86116e8",
        "118051d4b2a6559e",
        "0aa7e37825239ed9",
        "db3e53a360a0f4eb",
        "c31495210d0db5e4",
        "619f08c8ea06c154",
        "55d9116a33ab4b24",
        "5595e31750ca85ce",
        "3ea070ab7ee29522",
        "715498120edc00f3",
        "dd6fd387e4a04e0a",
        "fafe1698b1deacc8",
        "40a7da87d1b4d211",
        "236f78303313e6a9",
    }
)

_FORBIDDEN_OUTSIDE_BYLINE = frozenset({"4a1c1a751d4b9773"})


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _phrases(line: str) -> set[str]:
    """Return the normalized unigrams and bigrams of one line."""
    tokens = re.sub(r"\W+", " ", line.lower()).split()
    out = set(tokens)
    out.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:]))
    return out


def _tracked_text_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [
        _REPO_ROOT / name
        for name in listed
        if name.strip() and Path(name).suffix in _TEXT_SUFFIXES
    ]


def test_no_real_names_or_ids_in_tracked_files():
    hits: list[str] = []
    for path in _tracked_text_files():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        banned = _FORBIDDEN
        if rel not in _BYLINE_FILES:
            banned = banned | _FORBIDDEN_OUTSIDE_BYLINE
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            if any(_digest(p) in banned for p in _phrases(line)):
                hits.append(f"{rel}:{number}")

    assert not hits, (
        "Real (non-synthetic) names, organizations, or internal IDs found at: "
        + ", ".join(hits)
        + ". Replace them with synthetic test data; see docs/TESTING.md."
    )
