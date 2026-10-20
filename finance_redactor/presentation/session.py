"""Shared per-upload session-state helpers for the Excel/PDF/Word flows.

Each flow keys its cached results on the uploaded file's name and a
``file_type`` tag, and gets a neutral download name per upload. Collected here
so the three flows don't each hand-roll their own copy of this bookkeeping.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import streamlit as st


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


def reset_on_new_upload(
    uploaded: Any,
    file_type: str,
    clear_keys: Iterable[str],
    *,
    force: bool = False,
) -> bool:
    """Clear stale cached results when a new file (or file type) is uploaded.

    Compares ``uploaded.name``/``file_type`` against what's already recorded
    in session_state; ``force`` allows a caller (Excel, which also depends on
    a ``df`` key surviving) to fold in an extra reset condition of its own.
    When a reset is triggered, records the new ``uploaded_name``/``file_type`` and
    pops each of ``clear_keys`` from session_state. Returns whether a reset
    happened, so callers can gate their own re-population (e.g. re-reading the
    upload into a DataFrame) on it.
    """
    is_new = (
        force
        or st.session_state.get("uploaded_name") != uploaded.name
        or st.session_state.get("file_type") != file_type
    )
    if is_new:
        st.session_state.pop("output_stem", None)
        st.session_state.uploaded_name = uploaded.name
        st.session_state.file_type = file_type
        for key in clear_keys:
            st.session_state.pop(key, None)
    return is_new
