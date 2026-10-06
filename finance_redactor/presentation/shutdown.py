"""Sidebar control that fully quits the app for a non-technical user.

Closing only the browser tab leaves the Streamlit server - and the console
window ``run.bat``/``run.sh`` opened - running in the background, still
holding the master list and NLP model in memory. This renders a
confirm-then-quit control that ends the whole process, which also allows that
console window to close on its own.
"""

from __future__ import annotations

import os
import threading

import streamlit as st

_CONFIRM_KEY = "shutdown_confirm_pending"
_QUITTING_KEY = "shutdown_in_progress"


def render_quit_control() -> None:
    """Render a sidebar button that shuts the whole app down, with one confirm step."""
    with st.sidebar:
        st.divider()

        if st.session_state.get(_QUITTING_KEY):
            st.success("Closing the app - you can close this browser tab now.")
            # os._exit, not sys.exit/st.stop: the Streamlit server keeps
            # running for other sessions/threads, so only a hard process
            # exit actually stops it. The short delay gives the message
            # above time to reach the browser before the connection drops.
            threading.Timer(1.5, os._exit, args=(0,)).start()
            st.stop()

        if st.session_state.get(_CONFIRM_KEY):
            st.warning("Close the app now? Anything not yet downloaded will be lost.")
            col_yes, col_cancel = st.columns(2)
            if col_yes.button("Yes, close it", type="primary", width="stretch"):
                st.session_state[_QUITTING_KEY] = True
                st.rerun()
            if col_cancel.button("Cancel", width="stretch"):
                st.session_state[_CONFIRM_KEY] = False
                st.rerun()
            return

        if st.button(
            "Close the app",
            help="Fully quits the tool and closes its window",
            width="stretch",
        ):
            st.session_state[_CONFIRM_KEY] = True
            st.rerun()
