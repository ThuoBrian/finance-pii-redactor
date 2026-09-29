# AGENTS.md

Instructions for coding agents working in this repository. Humans should start
with [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## What this is

A local Streamlit app that pseudonymizes names (and masks bank and payment
details) in Excel, PDF and Word files. It is a PII tool, and it runs on
machines that hold real, Confidential data.

## Commands

Run through `uv`; recipes live in the `justfile`.

```bash
uv run just setup      # install runtime + dev dependencies from uv.lock
uv run just check      # everything CI runs: lint, format check, mypy, tests, codespell
uv run just test       # pytest with the 80% coverage gate
uv run just run        # start the app on 127.0.0.1
```

Run `uv run just check` before calling a change done.

## Rules

- **Never use real data.** No real names, organizations, internal IDs or
  master-list content in code, tests, docs, commits or PR text. Use made-up
  data (see [docs/user-testing.md](docs/user-testing.md#test-data)).
  `tests/test_no_real_pii_in_repo.py` enforces this for known values.
- **Never read or commit anything under `data/`** other than
  `data/README.md`, and never commit `.xlsx`, `.pdf`, `.docx` or
  `*_crosswalk.csv` files. They are gitignored for a reason.
- **Keep the layers.** `domain/` imports only the standard library, `application/`
  imports only `domain/`, and only `app.py` wires in `infrastructure/`.
  `tests/test_layers.py` enforces this. Read
  [ARCHITECTURE.md](ARCHITECTURE.md) before moving code between layers.
- **Lean toward over-redaction.** A missed name is a data leak; a false
  positive is an inconvenience. Don't loosen detection to fix a false
  positive; users can already reject one per document in the UI.
- **Keep `run.bat` and `run.sh` pure ASCII with LF endings.** See
  [docs/troubleshooting.md](docs/troubleshooting.md).
- Tests mirror the package: a module in `finance_redactor/domain/` is tested
  in `tests/domain/`.
- Record user-visible changes under `[Unreleased]` in
  [CHANGELOG.md](CHANGELOG.md).

## Where to look

- [ARCHITECTURE.md](ARCHITECTURE.md): layers, composition root, caching.
- [docs/troubleshooting.md](docs/troubleshooting.md): known problems and
  deliberate design limits. Check here before "fixing" something that looks
  like a bug.
- [data/README.md](data/README.md): master-list file format.
