# Contributing

This covers the local dev loop for `finance_redactor`. For how to *use* the
app, see [README.md](README.md); for known issues, see
[docs/troubleshooting.md](docs/troubleshooting.md).

## Setup

Requires Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ThuoBrian/finance-pii-redactor.git
cd finance-pii-redactor
uv sync --python 3.12
```

This installs runtime and dev dependencies (`ruff`, `mypy`, `pytest`,
`codespell`, type stubs) from `uv.lock`, including the pinned
`en_core_web_lg` spaCy model.

Common commands live in the `justfile`. Install [`just`](https://just.systems/)
once so you can call it directly:

```bash
winget install Casey.Just   # Windows
brew install just           # macOS
```

Run `just` to list the recipes. A copy of `just` also comes with the dev
dependencies, so `uv run just <recipe>` works without a system install (CI
uses that).

Run the app locally with:

```bash
just run
```

## Before opening a PR

CI runs exactly this command (`.github/workflows/ci.yml` calls the
justfile's `check` recipe), so run it locally first:

```bash
just check
```

`just fmt` fixes formatting in place. If you'd rather not use
`just`, these are the underlying commands:

```bash
uv run ruff check app.py finance_redactor/ tests/ scripts/
uv run ruff format --check app.py finance_redactor/ tests/ scripts/
uv run mypy app.py finance_redactor/
uv run pytest
uv run codespell
```

`uv run ruff format` (without `--check`) will fix formatting in place.
`uv run pytest` enforces an 80% coverage floor on `finance_redactor/`,
excluding `finance_redactor/presentation/` (Streamlit UI code — see the
`[tool.coverage.run]` comment in `pyproject.toml` for why).

If you changed prose in `README.md`, `docs/`, or `data/README.md`, also run
[Vale](https://vale.sh/) (config in `.vale.ini`):

```bash
just docs
```

## Pull requests

Fill in `.github/PULL_REQUEST_TEMPLATE.md` — it prompts for which layer(s)
your change touches (domain / application / infrastructure / presentation),
deployment notes (e.g. "re-run `uv sync`", "set `FPR_MASTER_LIST_DIR`"), and
the same checklist above. Commit messages in this repo generally follow
`type: summary` (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `ci:`) —
match the existing style in `git log`.

**Never include real names, real master-list content, or any other
Confidential/Highly Confidential data in a commit, PR description, or
comment.** Use synthetic test data (see
[docs/user-testing.md](docs/user-testing.md#test-data)).

## Where things live

- `finance_redactor/domain/` — pure business logic (pseudonymization, rules,
  fuzzy matching, custom words). No I/O, no Streamlit.
- `finance_redactor/application/` — use cases that orchestrate a redaction
  flow for one file format (`redact_excel.py`, `redact_pdf.py`,
  `redact_docx.py`).
- `finance_redactor/infrastructure/` — adapters: detection (Presidio/spaCy),
  document I/O (openpyxl/PyMuPDF/python-docx), and the master-list
  repository.
- `finance_redactor/presentation/` — Streamlit widgets and session state.
  Deliberately excluded from the coverage gate (see above); test it manually.
- `app.py` — the Streamlit composition root.
- `tests/` — one test file per module, in folders that mirror the layers
  (`tests/domain/`, `tests/application/`, …). Cross-cutting tests
  (`test_config.py`, the layer guard, the PII guard) and `conftest.py` sit
  at the top.

For the layer rules, composition root and caching, see
[ARCHITECTURE.md](ARCHITECTURE.md).

## Maintainer

Brian Thuo, Systems Engineer — bthuo@poverty-action.org
