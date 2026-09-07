"""Shared per-upload session-state helpers for the Excel/PDF/Word flows.

Each flow keys its cached results on the uploaded file's name and a
``file_type`` tag, and derives a filesystem-safe base name for download
filenames from that same upload. Collected here so the three flows don't each
hand-roll their own copy of this bookkeeping.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import streamlit as st


def sanitize_base_name(filename: str) -> str:
    """Return ``filename``'s stem with anything but word chars/hyphens as '_'.

    Used to build safe download filenames (e.g. ``My File.xlsx`` ->
    ``My_File``) from a user-supplied upload name.
    """
    return re.sub(r"[^\w\-]", "_", filename.rsplit(".", 1)[0])


def reset_on_new_upload(
    uploaded: Any,
    file_type: str,
    clear_keys: Iterable[str],
    *,
    force: bool = False,
) -> bool:
    """Clear stale cached results when a new file (or file type) is uploaded.

    Compares ``uploaded.name``/``file_type`` against what's already recorded
    in session_state; ``force`` lets a caller (Excel, which also depends on a
    ``df`` key surviving) fold in an extra reset condition of its own. When a
    reset is triggered, records the new ``uploaded_name``/``file_type`` and
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
        st.session_state.uploaded_name = uploaded.name
        st.session_state.file_type = file_type
        for key in clear_keys:
            st.session_state.pop(key, None)
    return is_new
