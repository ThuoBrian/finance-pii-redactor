# Developer commands. Run `uv run just` to list recipes.
# End users don't need this - they use run.bat / run.sh.

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Keep in sync with .github/workflows/ci.yml.
src := "app.py finance_redactor/ tests/ scripts/"

default:
    @just --list

# Install runtime and dev dependencies from uv.lock
setup:
    uv sync --python 3.12

# Start the app on localhost
# Ctrl+C makes Streamlit exit non-zero; don't report that as a recipe failure.
[no-exit-message]
run:
    uv run streamlit run app.py --server.address=127.0.0.1

lint:
    uv run ruff check {{src}}

# Format code in place
fmt:
    uv run ruff format {{src}}

fmt-check:
    uv run ruff format --check {{src}}

typecheck:
    uv run mypy app.py finance_redactor/

# Tests with the 80% coverage gate
test:
    uv run pytest

spell:
    uv run codespell

# Prose lint (needs Vale installed separately)
docs:
    vale README.md docs/ data/README.md

# Everything CI runs, in CI order
check: lint fmt-check typecheck test spell
