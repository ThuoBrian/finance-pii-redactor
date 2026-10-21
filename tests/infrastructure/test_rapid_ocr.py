"""Integration test for the RapidOCR adapter, run fully offline on made-up text.

This loads the real OCR model (a couple of seconds), unlike the rest of the
suite, because what matters here is that the bundled models work with no
network and that boxes come back in the picture's pixels.
"""

from __future__ import annotations

import socket

import fitz
import pytest

pytest.importorskip("rapidocr")

from finance_redactor.infrastructure.ocr.rapid_ocr import RapidOcrEngine  # noqa: E402


def _no_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("OCR tried to use the network")


def test_reads_made_up_text_offline_with_boxes_in_pixels(monkeypatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 130), "Paid to Jane Doe for field work.", fontsize=12)
    png = page.get_pixmap(dpi=200).tobytes("png")

    lines = RapidOcrEngine().read(png)

    texts = [line.text for line in lines]
    assert any("Jane Doe" in t for t in texts), texts
    line = next(line for line in lines if "Jane Doe" in line.text)
    x0, y0, x1, y1 = line.box
    # 72 pt and 130 pt at 200 dpi are 200 px and 361 px: the line sits there.
    assert 150 < x0 < 260 and y0 < 361 < y1 + 20
    assert line.score > 0.8
