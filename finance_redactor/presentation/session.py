"""Shared per-upload session-state helpers for the Excel/PDF/Word flows.

Each flow keys its cached results on the uploaded file's identity (name, size
and a hash of its bytes) and a ``file_type`` tag, and gets a neutral download name per upload. Collected here
so the three flows don't each hand-roll their own copy of this bookkeeping.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import streamlit as st

from finance_redactor.presentation.crosswalk_view import PDF_NAMES_TOGGLE_KEY

# The identity of the file the cached results were built from.
UPLOAD_IDENTITY_KEY = "upload_identity"
# The PDF Review step's table-column picker (its live value).
PDF_COLUMNS_KEY = "pdf_columns_pending"

# Everything built from one upload, in every format. One list for all three
# flows, so a Word upload after a PDF also drops the PDF's buffers (and the
# names-file toggle, which must start off for every new document).
RESULT_KEYS = (
    # Excel
    "sheets",
    "formats",
    "findings",
    "scan_sheets",
    "scan_columns",
    "redacted_sheets",
    "crosswalk",
    "excel_excluded_applied",
    "excel_bytes",
    # PDF
    "pdf_scan_result",
    "pdf_buffer",
    "pdf_findings",
    "pdf_pages",
    "pdf_crosswalk",
    "pdf_bracketed",
    "pdf_links",
    "pdf_not_located",
    "pdf_all_findings",
    "pdf_excluded_applied",
    "pdf_columns_applied",
    PDF_COLUMNS_KEY,
    PDF_NAMES_TOGGLE_KEY,
    "pdf_run",
    "pdf_job_size",
    # Word
    "docx_scan_result",
    "docx_buffer",
    "docx_findings",
    "docx_blocks",
    "docx_crosswalk",
    "docx_links",
    "docx_all_findings",
    "docx_excluded_applied",
    "docx_run_words",
)
# Per-file state with a key per tab or per review table.
_RESULT_PREFIXES = ("excel_cols_", "excel_review_", "pdf_review_", "docx_review_")


def neutral_stem(now: datetime) -> str:
    """Return ``redacted-YYYYMMDD-HHMM``: a download name with nothing from the upload.

    The upload's own name can be a person's or a vendor's, so no part of it is
    reused for the redacted file or its mapping CSV.
    """
    return f"redacted-{now:%Y%m%d-%H%M}"


def output_stem() -> str:
    """Return this upload's download-name stem, fixed until the next upload.

    Kept in session state so every rerun, and both the redacted file and its
    mapping CSV, share one name. It is cleared by :func:`reset_on_new_upload`.
    """
    if "output_stem" not in st.session_state:
        st.session_state.output_stem = neutral_stem(datetime.now())
    return str(st.session_state.output_stem)


def upload_identity(uploaded: Any) -> tuple[str, int, str]:
    """Return ``(name, size, SHA-256 of the bytes)``: what makes an upload "the same file".

    The name alone is not enough: a file edited and uploaded again under the
    same name must not reuse the old scan, or the download would be built
    from the wrong document. Hashing the whole buffer is cheap next to a scan.
    """
    data = uploaded.getbuffer()
    return uploaded.name, len(data), hashlib.sha256(data).hexdigest()


def reset_on_new_upload(uploaded: Any, file_type: str, *, force: bool = False) -> bool:
    """Clear stale cached results when a new file (or file type) is uploaded.

    Compares :func:`upload_identity` and ``file_type`` against what's already
    recorded in session_state; ``force`` allows a caller (Excel, which also
    depends on a ``sheets`` key surviving) to fold in an extra reset condition
    of its own. When a reset is triggered, records the new identity and
    ``file_type`` and pops every :data:`RESULT_KEYS` key from session_state. Returns
    whether a reset happened, so callers can gate their own re-population
    (e.g. re-reading the upload into a DataFrame) on it.
    """
    identity = upload_identity(uploaded)
    is_new = (
        force
        or st.session_state.get(UPLOAD_IDENTITY_KEY) != identity
        or st.session_state.get("file_type") != file_type
    )
    if is_new:
        # A new file always starts at Options (see presentation/wizard.py).
        st.session_state["wizard_step"] = 2
        st.session_state.pop("output_stem", None)
        # Results, review state, and tab and column choices belong to the old
        # file; typed words and settings carry over, as they always have.
        for key in [k for k in st.session_state if str(k).startswith(_RESULT_PREFIXES)]:
            del st.session_state[key]
        for key in (*RESULT_KEYS, "excel_tabs"):
            st.session_state.pop(key, None)
        st.session_state[UPLOAD_IDENTITY_KEY] = identity
        st.session_state.file_type = file_type
    return is_new
