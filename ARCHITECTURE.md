# Architecture

How `finance_redactor` is put together. For using the app, see
[README.md](README.md); for the dev loop, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Layers

The package follows a ports-and-adapters layout. Dependencies point inward
only:

```
frontend/ (React) ──HTTP──► presentation ──► application ──► domain
                                                 ▲
                            infrastructure ──────┘ (satisfies application/ports.py structurally)

app.py  wires concrete infrastructure into the application services
```

| Layer | Path | Holds | May import |
| --- | --- | --- | --- |
| Domain | `finance_redactor/domain/` | Pure logic: entities, pseudonymization, name variants, fuzzy suggestions, overlap rules, PDF text normalization, table columns from OCR lines, master-list quality findings | standard library only |
| Application | `finance_redactor/application/` | One use case per format (`redact_excel.py`, `redact_pdf.py`, `redact_docx.py`), the `Protocol` ports they depend on (`ports.py`), and result DTOs (`results.py`) | domain, pandas |
| Infrastructure | `finance_redactor/infrastructure/` | Adapters: `detection/` (Presidio, spaCy, pattern matching), `documents/` (openpyxl, PyMuPDF, python-docx), `ocr/` (RapidOCR, for scanned PDF pages), `names/` (master-list workbook reader) | domain, `config`, third-party libraries |
| Presentation | `finance_redactor/presentation/` | The local web API (`api/`: FastAPI routers per format, plus master list, uploads, downloads), the in-memory job store (`jobs.py`), request checks (`security.py`), response models (`schemas.py`), presenters that turn results into UI-ready tables and wording, and the built React bundle (`static/`) | application, domain, `config`, FastAPI, pandas |

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

`app.py` is the only file that knows about concrete adapters. `create_app()`
builds an `AppContext` (`presentation/api/context.py`) holding:

- `load_master_list` and `refresh_master_list` (see Caching below);
- one factory per format (`excel_service`, `docx_service`, `pdf_service`) that
  builds the use case on the current master list;
- the Excel gateway, the PDF opener (for page previews) and the job store.

It hands the context to `build_api()`, which mounts the routers, the request
guard and the static bundle. Routers reach the context through the `Context`
dependency and never import infrastructure, so the API tests run against a
fake composition root (`tests/presentation/api_fakes.py`). The helpers every
router shares live next to it in `api/context.py`: `job_for` (look up a job,
404 or 409), `scanned_state` and `start_or_409`. Review payloads for every
format come from `api/review.py`, built on `presenters.review_terms`.

`python app.py` (what `run.bat`, `run.sh` and `just run` call) serves it with
uvicorn on `127.0.0.1:8501` (`FPR_PORT` overrides the port), warms the NLP
model and master list in the background, and opens the browser. **Close the
app** in the interface ends the process.

## The interface

`frontend/` is a Vite + React + TypeScript app styled with Tailwind, with
Radix primitives for menus and dialogs and TanStack Query for server state.
`just web-build` writes it to `finance_redactor/presentation/static/`, which
is committed so end users never need Node. CI rebuilds it and fails if the
result differs from what is committed.

The page shows one stage at a time: File (upload, then settings), Review and
Download. The step lives in React state; each format has one flow component
(`components/excel/`, `docx/`, `pdf/`) that stays mounted across the settings,
Review and Download, so choices survive going Back. What the flows share is
in one place: `useFormatFlow` (scan, progress, review, apply, downloads),
`OptionsFooter`, `ScanProgress`, and `DownloadStep`/`DownloadCards`. Review is
shared too (`components/review/`): the findings list, a side panel (preview,
mapping, where found) and a sticky footer with Apply and Continue. Continue waits
while ticks, typed words or table columns are not applied, because the
download would otherwise be built from an older choice.

## Jobs and background work

An upload becomes a `Job` in the in-memory `JobStore`: its bytes, a neutral
download stem (`redacted-YYYYMMDD-HHMM`, nothing from the upload's name) and
per-format state (scan result, applied exclusions, outputs). Nothing is
written to disk. A new upload replaces the previous job, Start over deletes
it, and a job idle for four hours is dropped.

Scans run in a background thread (`JobStore.start_task`); the interface
polls `GET /api/jobs/{id}` for status and progress. A failed task shows a
generic message and logs only the exception type, never its text, which
could quote a cell or a name. Messages written for the user
(`UserFacingError`) are shown as they are.

Scan and redact stay separate, as in the use cases: applying review choices,
typed words or PDF table columns is a rebuild over the cached scan, with no
re-detection and no OCR.

## Security

The server binds to `127.0.0.1` only. Because any web page the user has
open can still send requests to localhost, `security.py` adds:

- a `Host` allowlist (`127.0.0.1:<port>`, `localhost:<port>`), against DNS
  rebinding;
- a required `X-FPR-Client` header on every `/api` call, with no CORS
  middleware, so cross-site pages cannot make the call (the browser's
  preflight fails); downloads go through `fetch` so they carry it too;
- `Content-Security-Policy: default-src 'self'` and related headers on every
  response. The bundle uses system fonts and loads nothing from outside, so
  nothing leaves the machine.

Uploads are checked by extension, magic bytes and size (200 MB). The API
docs pages (`/docs`, `/openapi.json`) are off.

## Caching

- **NLP engine.** The spaCy model loads once per process.
- **Master-list bundle.** Parsed rows, recognizers and the detection engine
  (`_build_master_list_bundle`), cached on the workbook's path and
  modification time and rebuilt when either changes, on the next request
  that needs it. **Refresh** in the master-list popover clears it outright,
  for the case where the modification time has not changed yet (for example
  a Box Drive sync still copying the file down).
- **OCR engine.** Created on first use; `None` when RapidOCR is not
  installed, in which case scanned pages are reported but not read.

## Outputs and sensitivity

Each flow returns the redacted file plus a mapping back to the originals: a
separate crosswalk CSV of real names for Excel and Word (never inside the
redacted file, so that file stays Internal), and for PDF a mapping of labels to internal IDs that holds
no names (plus, only if the user switches it on, a second Confidential CSV
with names, built by a separate function so the default file can never gain a
name column). The "Which file is safe to share" section of the README gives the data
classification for each. The master list is what turns an ID back into a
name, so it and every real input document stay out of git (`data/*`,
`*.xlsx`, `*.pdf`, `*.docx`, `*_crosswalk.csv` in `.gitignore`).

## Tests

`tests/` mirrors the layers (`tests/domain/`, `tests/application/`,
`tests/infrastructure/`, `tests/presentation/`). Cross-cutting tests sit at
the top: `test_config.py`; `test_layers.py`, which enforces the layer rules;
and `test_no_real_pii_in_repo.py`, which fails if a known real name or ID
reappears in any tracked file.

The web API is tested end to end per format with FastAPI's `TestClient`, the
real use cases and document adapters, and a fake detector
(`tests/presentation/test_api*.py`). Coverage is enforced at 80% over the
whole package, presentation included. mypy covers `app.py` and the package,
not the tests.

The interface has its own tests (`frontend/src/test/`, Vitest and Testing
Library), run with `just web-test`. The screens are also checked by hand
using [docs/user-testing.md](docs/user-testing.md).
