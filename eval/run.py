"""Run the shipped pipeline over a synthetic corpus and report leaks.

Usage: ``uv run python -m eval.run [--seed 1] [--size 200] [--ocr]
[--baseline eval/results/<file>.json]``. ``just eval`` runs the defaults.

Wired like ``app.py`` (it reuses its builders), so it measures exactly what
ships. The master list is the synthetic one, written to a temp folder; the
real ``data/`` folder is never read.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from app import (
    _build_master_list_bundle,
    _docx_service,
    _excel_service,
    _pdf_service,
)
from eval import corpus, extract, scoring
from finance_redactor.config import Settings
from finance_redactor.infrastructure.detection.presidio_detector import PresidioEngine
from finance_redactor.infrastructure.documents.excel_gateway import (
    OpenpyxlExcelGateway,
)

_REPO = Path(__file__).resolve().parent.parent
_RESULTS = _REPO / "eval" / "results"


def main(argv: list[str] | None = None) -> int:
    """Build the corpus, redact it, score it, write the report."""
    args = _parse(argv)
    started = time.perf_counter()
    built = corpus.build(args.seed, args.size, ocr=args.ocr)
    print(f"Built {len(built.docs)} documents, {len(built.gold)} gold values.")

    with tempfile.TemporaryDirectory() as tmp:
        names_dir = Path(tmp)
        if names_dir.resolve().is_relative_to(_REPO / "data"):
            raise SystemExit("refusing to run against the real data/ folder")
        settings = Settings(names_dir=names_dir)
        settings.master_list_file.write_bytes(built.master_list)
        outputs, detections = _redact_all(built, settings, ocr=args.ocr)

    report = scoring.score(built.gold, outputs, detections)
    report["run"] = {
        "seed": args.seed,
        "size": args.size,
        "ocr": args.ocr,
        "seconds": round(time.perf_counter() - started, 1),
    }
    _print(report)
    path = _write(report, args)
    print(f"\nReport: {path}")
    return _compare(report, args.baseline) if args.baseline else 0


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--size", type=int, default=200, help="number of documents")
    parser.add_argument("--ocr", action="store_true", help="include scanned PDFs")
    parser.add_argument("--baseline", type=Path, help="earlier report to compare")
    return parser.parse_args(argv)


def _redact_all(
    built: corpus.Corpus, settings: Settings, *, ocr: bool
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Run each document through its real service, as the UI would."""
    ocr_engine = None
    read_png: extract.OcrRead | None = None
    if ocr:
        from finance_redactor.infrastructure.ocr.rapid_ocr import RapidOcrEngine

        engine = RapidOcrEngine()
        ocr_engine = engine

        def read_png(png: bytes) -> str:
            return "\n".join(line.text for line in engine.read(png))

    state = _build_master_list_bundle(
        settings, PresidioEngine._create_nlp_engine(settings), None
    )
    excel = _excel_service(settings, state)
    docx = _docx_service(settings, state)
    pdf = _pdf_service(settings, state, ocr_engine)
    gateway = OpenpyxlExcelGateway()
    entities = list(settings.supported_entities)
    threshold = settings.default_threshold

    outputs: dict[str, str] = {}
    detections: dict[str, list[str]] = {}
    for number, doc in enumerate(built.docs, start=1):
        if doc.file_type == "xlsx":
            sheets = gateway.read_sheets(BytesIO(doc.data))
            columns = {name: gateway.text_columns(df) for name, df in sheets.items()}
            scan = excel.scan_workbook(sheets, columns, entities, threshold)
            redacted, _ = excel.redact_workbook(sheets, scan, columns)
            data = gateway.write([(s.name, s.data, s.highlighted) for s in redacted])
            found = _excel_texts(scan)
        elif doc.file_type == "docx":
            docx_scan = docx.scan(BytesIO(doc.data), entities, threshold)
            result = docx.redact(BytesIO(doc.data), docx_scan, [])
            data, found = result.data, [f.detected_text for f in result.findings]
        else:
            pdf_scan = pdf.scan(BytesIO(doc.data), read_scans=ocr)
            pdf_result = pdf.redact(BytesIO(doc.data), pdf_scan, [])
            data = pdf_result.data
            found = [f.detected_text for f in pdf_result.findings]
        outputs[doc.name] = extract.text_of(doc.file_type, data, read_png)
        detections[doc.name] = found
        if number % 25 == 0:
            print(f"  {number}/{len(built.docs)} redacted")
    return outputs, detections


def _excel_texts(scan: Any) -> list[str]:
    texts = [d.text for cell in _cells(scan) for d in cell.detections]
    texts += [d.text for found in scan.tab_names.values() for d in found]
    texts += [
        d.text
        for by_header in scan.headers.values()
        for found in by_header.values()
        for d in found
    ]
    return texts


def _cells(scan: Any) -> list[Any]:
    return [cell for sheet in scan.sheets.values() for cell in sheet.findings]


def _print(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("\n== Summary ==")
    print(
        f"Recall {_pct(summary['recall'])} "
        f"({summary['leaked']} of {summary['gold']} values leaked)  "
        f"Precision {_pct(summary['precision'])} "
        f"({summary['false_positives']} of {summary['detections']} detections)"
    )
    print(
        f"Negative probes redacted: {summary['negatives_redacted']}  "
        f"Known-limit leaks (not counted): {summary['known_limit_leaked']}"
    )
    types = [t for t in corpus.FILE_TYPES if t in report["precision"]]
    print("\n== Leaked / total, by scenario ==")
    print(_row("scenario", types))
    for category, cells in report["recall"].items():
        print(_row(category, [_cell(cells.get(t), "leaked") for t in types]))
    print("\n== Wrongly redacted / total, negative probes ==")
    for category, cells in report["negatives"].items():
        print(_row(category, [_cell(cells.get(t), "redacted") for t in types]))
    print("\n== Precision by file type ==")
    for file_type in types:
        c = report["precision"][file_type]
        print(
            f"  {file_type:<12} {c.get('fp', 0)} false of {c.get('tp', 0) + c.get('fp', 0)}"
        )
    if report["top_false_positives"]:
        print("\n== Most frequent false positives ==")
        for text, count in report["top_false_positives"][:15]:
            print(f"  {count:>4}  {text}")


def _row(label: str, cells: list[str]) -> str:
    return f"  {label:<24}" + "".join(f"{c:>14}" for c in cells)


def _cell(counts: dict[str, int] | None, key: str) -> str:
    return f"{counts.get(key, 0)}/{counts['total']}" if counts else "-"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _write(report: dict[str, Any], args: argparse.Namespace) -> Path:
    _RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = _RESULTS / f"seed{args.seed}-size{args.size}-{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def _compare(report: dict[str, Any], baseline_path: Path) -> int:
    """Print deltas; return 1 if more values leak than in the baseline."""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if baseline["run"]["seed"] != report["run"]["seed"] or (
        baseline["run"]["size"] != report["run"]["size"]
    ):
        print("Warning: baseline used a different seed or size; deltas are rough.")
    now, then = report["summary"], baseline["summary"]
    print("\n== Against baseline ==")
    for key in ("leaked", "false_positives", "negatives_redacted"):
        print(
            f"  {key:<20} {then[key]:>6} -> {now[key]:<6} ({now[key] - then[key]:+d})"
        )
    if now["leaked"] > then["leaked"]:
        print("More values leak than in the baseline.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
