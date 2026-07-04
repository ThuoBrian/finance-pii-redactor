# Finance PII Redactor

An offline desktop tool that **pseudonymizes** names and organization names in
Excel and PDF files locally. Each detected name is replaced with a stable ID
(e.g. `STF-91345`, `VND-1045`, `FND-7745`) rather than a generic `[PERSON]`
label, so the same entity maps to the same ID everywhere — cross-row and
cross-file patterns survive for error-checking and fraud monitoring while the
real identities are removed. All processing happens on your machine; no data
leaves the laptop.

It uses Microsoft Presidio with a spaCy `en_core_web_lg` model for detection,
openpyxl for Excel output, and PyMuPDF for PDF text replacement.

## Run it

- **Windows:** double-click `run.bat`
- **macOS / Linux:** run `run.sh`

The first run installs the Python environment and downloads the spaCy model
(~380 MB); later starts are fast. The launcher opens the app in your browser.

## Sharing with your team

To hand the tool to non-technical colleagues:

1. Run **`package.bat`** (Windows) or **`./package.sh`** (macOS/Linux). This builds
   a lightweight source zip at `../finance-pii-redactor.zip` (no environment or
   model bundled — just the code).
2. Share that zip (email, shared drive, etc.). Each teammate extracts it and
   double-clicks `run.bat`.
3. Their **first run** installs everything automatically — the Python environment
   *and* the language model — in one step (~400 MB, a few minutes, internet needed
   once). Every run after that is fast and fully offline.

Because the spaCy model is now a tracked dependency, there is no separate
model-download step to fail — the first `run.bat` handles it end to end.

## Documentation

- **[GUIDE.md](GUIDE.md)** — plain-language walkthrough for end users: what the
  tool does, how to run it, and data-handling caveats.
- **[CLAUDE.md](CLAUDE.md)** — architecture and developer reference (clean-
  architecture layers, master list, dev commands).
- **[GOTCHA.md](GOTCHA.md)** — known issues and fixes.

## Data classification

Approved for **Internal** data only under IPA's data-classification policy — do
not use for Confidential or Highly Confidential data.

**Important:** the name → pseudonym **crosswalk** the tool produces is the
re-identification key and is itself **Confidential**. Store and handle it
accordingly, and never share it alongside the pseudonymized output file.
