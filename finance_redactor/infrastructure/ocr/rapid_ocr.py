"""OCR adapter: RapidOCR on ONNX Runtime.

Implements the :class:`OcrEngine` port. The models ship inside the ``rapidocr``
package, so reading works offline once the app is installed; nothing is
downloaded at run time for the default models. The engine loads on first use
(about two seconds), so a session that never meets a scanned page never pays
for it.

RapidOCR logs model paths at INFO level; that is quietened here. It never logs
the text it reads, and neither does this adapter.
"""

from __future__ import annotations

import logging
from typing import Any

from finance_redactor.domain.ocr import OcrLine

_LOGGER_NAME = "RapidOCR"


class RapidOcrEngine:
    """Reads printed text from a PNG of a page."""

    def __init__(self) -> None:
        """Create the adapter; the model itself loads on the first ``read``."""
        self._engine: Any = None

    def read(self, png: bytes) -> list[OcrLine]:
        """Return the lines read from ``png``, with boxes in its pixels."""
        if self._engine is None:
            from rapidocr import RapidOCR

            self._engine = RapidOCR()
            logging.getLogger(_LOGGER_NAME).setLevel(logging.WARNING)
        result = self._engine(png)
        if result.boxes is None:
            return []
        lines = []
        for box, text, score in zip(
            result.boxes, result.txts, result.scores, strict=True
        ):
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            lines.append(
                OcrLine(str(text), (min(xs), min(ys), max(xs), max(ys)), float(score))
            )
        return lines
