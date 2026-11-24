# Developer commands. Run `just` to list recipes (install: winget install
# Casey.Just). Without a system just, `uv run just` works too.
# End users don't need this - they use run.bat / run.sh.

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Paths the lint and format recipes cover.
src := "app.py finance_redactor/ tests/ eval/"

default:
    @just --list

# Install runtime and dev dependencies from uv.lock
setup:
    uv sync --python 3.12

# Ctrl+C makes the server exit non-zero; don't report that as a recipe failure.
# Start the app on localhost (serves the committed UI bundle)
[no-exit-message]
run:
    uv run python app.py

# Install the frontend's dependencies (needs Node; end users never do)
web-setup:
    npm --prefix frontend ci

# Rebuild the UI bundle into finance_redactor/presentation/static/ (commit it)
web-build:
    npm --prefix frontend run build

# Frontend type check and tests
web-test:
    npm --prefix frontend run typecheck
    npm --prefix frontend test

# UI dev server with hot reload on :5173; run `just run` alongside for the API
web-dev:
    npm --prefix frontend run dev

lint:
    uv run ruff check {{src}}

# Format code in place
fmt:
    uv run ruff format {{src}}

fmt-check:
    uv run ruff format --check {{src}}

typecheck:
    uv run mypy app.py finance_redactor/ eval/

# Tests with the 80% coverage gate
test:
    uv run pytest

# Detection test harness: synthetic corpus through the real pipeline (slow)
eval *args:
    uv run python -m eval.run {{args}}

spell:
    uv run codespell

# Prose lint (needs Vale installed separately)
docs:
    vale README.md docs/ data/README.md

# Everything CI runs (.github/workflows/ci.yml calls this recipe)
check: lint fmt-check typecheck test spell
