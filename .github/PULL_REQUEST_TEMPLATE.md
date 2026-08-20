## Description

<!-- What does this PR do, and why? -->

## Type of Change

- [ ] Emergency fix (bypassed normal review process)
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature or function
- [ ] Documentation only
- [ ] Chore / maintenance (dependencies, tooling, refactor with no behavior change)

## What Changed

<!-- Bullet list of concrete changes -->

## Code Affected

- [ ] Domain layer (`finance_redactor/domain/`)
- [ ] Application layer / use cases (`finance_redactor/application/`)
- [ ] Infrastructure adapters (`finance_redactor/infrastructure/` - detection, documents, names)
- [ ] Presentation / Streamlit UI (`finance_redactor/presentation/`, `app.py`)
- [ ] Config (`finance_redactor/config.py`)
- [ ] Master list / data handling (`data/`, `FPR_MASTER_LIST_DIR` / in-app setup dialog)
- [ ] Launcher/installer scripts (`run.bat`, `run.sh`, `install.ps1`, `install.sh`)
- [ ] Tests (`tests/`)
- [ ] Documentation (`README.md`, `CLAUDE.md`, `docs/GOTCHA.md`, `data/README.md`)
- [ ] CI / tooling (`.github/workflows/`, `pyproject.toml`)
- [ ] None of the above

## Deployment Notes

<!-- Anything a user/teammate needs to do after this merges - e.g. re-run
     `uv sync` (new dependency), re-download via the installer, set/update
     FPR_MASTER_LIST_DIR, edit the master-list format. Write "N/A" if nothing
     is needed. -->

## Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check app.py finance_redactor/ tests/` and `ruff format --check` are clean
- [ ] `uv run codespell` is clean
- [ ] If docs changed: `vale README.md CLAUDE.md docs/ data/README.md` shows no new errors
- [ ] Tested manually end-to-end if this touches the UI or a file-format flow
- [ ] Docs updated (`CLAUDE.md`/`README.md`/`docs/GOTCHA.md`) if behavior changed
- [ ] No Confidential/Highly Confidential data (real names, real master-list content) appears anywhere in this PR's diff, description, or comments

## Links

<!-- Related issues, discussions, etc. N/A if none. -->

## Screenshots (if applicable)

<!-- Especially for UI changes - before/after is ideal. -->
