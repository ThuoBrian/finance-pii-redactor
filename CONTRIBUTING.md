# Contributing

This covers the local dev loop for `finance_redactor`. For how to *use* the
app, see [README.md](README.md); for known issues, see
[docs/GOTCHA.md](docs/GOTCHA.md).

## Setup

Requires Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ThuoBrian/finance-pii-redactor.git
cd finance-pii-redactor
uv sync --python 3.12
```

This installs runtime and dev dependencies (`ruff`, `mypy`, `pytest`,
`codespell`, plus type stubs) from `uv.lock`, including the pinned
`en_core_web_lg` spaCy model.

Run the app locally with:

```bash
uv run streamlit run app.py
```

## Before opening a PR

Run the same checks CI runs, in the same order it runs them
(`.github/workflows/ci.yml`):

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
vale README.md docs/ data/README.md
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
[docs/TESTING.md](docs/TESTING.md#test-data)).

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
- `tests/` — one test file per module under `finance_redactor/`.

If you need more architectural detail than this, ask the maintainer for
`CLAUDE.md` (kept local, not tracked in this repo).
