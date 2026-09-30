# Architecture

How `finance_redactor` is put together. For using the app, see
[README.md](README.md); for the dev loop, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Layers

The package follows a ports-and-adapters layout. Dependencies point inward
only:

```
presentation ──► application ──► domain
                     ▲
infrastructure ──────┘ (satisfies application/ports.py structurally)

app.py  wires concrete infrastructure into the application services
```

| Layer | Path | Holds | May import |
| --- | --- | --- | --- |
| Domain | `finance_redactor/domain/` | Pure logic: entities, pseudonymization, name variants, fuzzy suggestions, overlap rules, PDF text normalization, master-list quality findings | standard library only |
| Application | `finance_redactor/application/` | One use case per format (`redact_excel.py`, `redact_pdf.py`, `redact_docx.py`), the `Protocol` ports they depend on (`ports.py`), and result DTOs (`results.py`) | domain, pandas |
| Infrastructure | `finance_redactor/infrastructure/` | Adapters: `detection/` (Presidio, spaCy, pattern matching), `documents/` (openpyxl, PyMuPDF, python-docx), `names/` (master-list workbook reader) | domain, `config`, third-party libraries |
| Presentation | `finance_redactor/presentation/` | Streamlit flows per format, shared widgets, session state, presenters that turn results into UI-ready tables and files | application, domain, `config`, Streamlit, pandas |

`finance_redactor/config.py` holds `Settings`, the single source of tunable
values (thresholds, entity types, masks, master-list location). Presentation,
infrastructure and `app.py` read it; domain and application take the values
they need as constructor arguments instead.

Infrastructure never imports application: adapters satisfy the ports in
`application/ports.py` by shape, not inheritance. Keep it that way; a use case
that needs a new capability gets a new port, not a direct import.
`tests/test_layers.py` enforces the "May import" column above and fails on
any import that points the wrong way.

## Composition root

`app.py` is the only file that knows about concrete adapters. On each
Streamlit rerun it:

1. Resolves `Settings` fresh via `current_settings()`, so a master-list folder
   chosen in the in-app setup dialog applies on the next rerun.
2. Loads cached resources (see below).
3. Routes the upload by extension to `run_excel_flow`, `run_pdf_flow` or
   `run_docx_flow`, handing each one a service built from the matching
   adapters.

## Caching

Streamlit reruns the whole script on every interaction, so expensive objects
are cached with `@st.cache_resource`:

- **NLP engine.** The spaCy model loads once per process.
- **Master-list bundle.** Parsed rows, recognizers and the detection engine,
  keyed on the workbook's path and modification time. Editing the workbook,
  or pointing at a different folder, rebuilds it. Streamlit only re-checks
  the key on a rerun, never on a timer, so an edit shows up after the next
  widget interaction or page reload.

## Outputs and sensitivity

Each flow returns the redacted file plus a mapping back to the originals: a
Crosswalk sheet inside the Excel output, a separate crosswalk CSV of real
names for Word, and for PDF a mapping of labels to internal IDs that holds
no names. The "Which file is safe to share" section of the README gives the data
classification for each. The master list is what turns an ID back into a
name, so it and every real input document stay out of git (`data/*`,
`*.xlsx`, `*.pdf`, `*.docx`, `*_crosswalk.csv` in `.gitignore`).

## Tests

`tests/` mirrors the layers (`tests/domain/`, `tests/application/`,
`tests/infrastructure/`, `tests/presentation/`). Cross-cutting tests sit at
the top: `test_config.py`; `test_layers.py`, which enforces the layer rules;
and `test_no_real_pii_in_repo.py`, which fails if a known real name or ID
reappears in any tracked file.

Coverage is enforced at 80% over domain, application and infrastructure.
`finance_redactor/presentation/` is excluded from the measured total
(`[tool.coverage.run]` in `pyproject.toml`) because it is Streamlit widget
and session-state code with little to unit-test; it is checked by hand using
[docs/user-testing.md](docs/user-testing.md). mypy covers `app.py` and the
package, not the tests.
