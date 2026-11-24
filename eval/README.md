# Detection test harness

Measures how many names the redactor misses (leaks) and how much it flags
wrongly, per file type and per kind of name. Run it before and after any
change to detection, so the change is judged on numbers rather than on a
handful of examples.

```bash
just eval                       # 200 documents, seed 1 (a few minutes)
just eval --size 30             # quick look
just eval --ocr                 # add scanned PDFs (much slower)
just eval --baseline eval/results/<earlier>.json
```

## What it does

1. **Builds a synthetic corpus** (`corpus.py`): a master list in the
   [documented format](../data/README.md#file-format) plus Excel, Word and PDF
   files. Every name is invented (`names.py`), and every value placed in a
   document is recorded as gold, so nothing is labelled by hand. The same
   seed always gives the same corpus.
2. **Runs the shipped pipeline** (`run.py`). The services are built with
   `app.py`'s own builders and the UI's default entities and threshold, and
   the synthetic master list sits in a temp folder. The real `data/` folder
   is never read.
3. **Checks the output** (`extract.py`, `scoring.py`). A gold value still
   readable in the redacted file is a leak. This checks what a reader would
   see, so a PDF term that was detected but couldn't be found on the page
   still counts.

Nothing generated is written into the repository except the JSON report in
`eval/results/` (gitignored).

## Reading the report

- **Recall**: the share of gold values that did not leak. Counts the
  scenarios in `scenarios.RECALL` plus the format-specific ones.
- **Known limits**: surnames on their own and `Surname, Given` order are
  documented as unmatched ([troubleshooting](../docs/troubleshooting.md)).
  Their leaks are shown, not counted against recall.
- **Precision**: the share of detections that overlap a gold name. A
  detection sharing a word (or the start of one, for PDF line breaks) with
  a gold value counts as a hit.
- **Negative probes**: phrases such as "Force Majeure" or "Petty Cash" that
  should survive. "Wrongly redacted" is how many disappeared.

With `--baseline`, the run prints the change in leaks and false positives
and exits non-zero if more values leak than before. Compare runs with the
same seed and size.

## Limits

- The corpus is template sentences, not real documents. It finds
  regressions and compares options well; it doesn't predict the leak rate
  on real files.
- Scanned-PDF output is read back with the same OCR engine the app uses. A
  surviving name that OCR misreads is not counted, so scanned leak counts
  are a lower bound.
- PDF tables are plain aligned text, not ruled tables, so the
  table-column feature isn't exercised.

## Adding a scenario

Add the category to `scenarios.py` (and templates if it is a sentence), make
`corpus._items` place it, and run `uv run pytest tests/eval`. That test
proves every gold value is really in its document.
