# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
the `version` field in `pyproject.toml`.

## [Unreleased]

Nothing yet — add entries here as changes are made, then move them under a
new version heading when `pyproject.toml`'s version is bumped.

## [0.1.0] - 2026-09-07

Initial development version. No tagged releases yet; this summarizes the
project's history to date.

### Added

- Excel, PDF, and Word redaction flows, pseudonymizing names/organizations to
  stable ID codes from a master list (`data/Names List - Organized.xlsx`).
- Master-list data-quality checks on load: cross-category duplicates,
  conflicting or reused `Internal ID`s, blank IDs, and ambiguous common-word
  names.
- Support for one shared master list across a team, via the
  `FPR_MASTER_LIST_DIR` environment variable or an in-app "Set up your
  shared master list" dialog.
- A **🔄 Refresh master list** button so edits are picked up without
  restarting the app.
- Crosswalk output: an embedded second sheet in Excel, or a separate CSV
  download for PDF/Word.
- Automatic email, website, and image/logo redaction in PDF; a
  words/phrases-to-redact box for anything PDF or Word can't detect
  automatically (names, codenames, case numbers).
- Fuzzy "possible match" suggestions for flagged auto-ids, and accent-folding
  so an unaccented approximation (`Jose Garcia`) matches an accented name
  (`José García`) in the words-to-redact box.
- Alias-aware master-list matching (`Ltd`/`Limited`, `&`/`and`, etc.) so one
  master-list row covers common surface-form variants.
- One-line installers (`install.ps1`, `install.sh`) and local launchers
  (`run.bat`, `run.sh`).
- CI (`ruff`, `ruff format`, `mypy`, `pytest` with an 80% coverage gate,
  `codespell`) and Dependabot.
- `docs/GOTCHA.md` (known issues/troubleshooting) and `docs/TESTING.md` (a
  user-acceptance testing checklist).

### Changed

- Master list migrated from plain-text lists to a single Excel workbook
  (`Names List - Organized.xlsx`).
- PDF detection scoped down to emails, websites, and images only — names and
  organizations are no longer guessed at in PDF (an intentional accuracy
  trade-off; see `docs/GOTCHA.md`), and must be typed into the
  words-to-redact box instead.
- Overlapping-span dedupe now prefers a master-list match over an overlapping
  model guess, regardless of which span is longer.
- `CustomNameRecognizer` switched from a per-name regex loop to an
  Aho-Corasick automaton for matching performance.
- Relicensed from MIT to Apache 2.0.

### Fixed

- PDF redaction in tightly single-spaced documents no longer bleeds into the
  line above the matched text.
- Legacy names with an ID appended in the name itself (`Jane Doe - 22463`)
  now match correctly.
- ALL-CAPS names are now detected (spaCy's NER model misses them in the
  original casing).

### Removed

- `CLAUDE.md` (internal architecture notes) is no longer tracked in this
  repository — kept local-only; ask the maintainer for a copy.
