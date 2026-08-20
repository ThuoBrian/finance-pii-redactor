"""In-app "Set up shared master list" dialog.

Allows a user to point the app at a shared Box (or similar) folder containing
``Names List - Organized.xlsx`` directly from the UI, instead of the OS
environment variable route (``FPR_MASTER_LIST_DIR``, documented in
``data/README.md``) - which needs a fresh terminal/process to take effect
(see ``docs/GOTCHA.md``'s "0 names" entry). The chosen folder is persisted
via ``finance_redactor.config.save_master_list_dir`` and takes effect on the
very next Streamlit rerun, with no app restart.

Triggered from ``app.py`` whenever the loaded master list has 0 entries - the
most common first-run state for a new teammate who hasn't pointed their
install at the team's shared folder yet.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from finance_redactor.config import save_master_list_dir

MASTER_LIST_FILENAME = "Names List - Organized.xlsx"


def master_list_exists_at(folder: str) -> bool:
    """Return True if ``folder`` contains the exact expected workbook filename.

    Pure/testable without Streamlit - matching is filename-exact (see
    ``data/README.md``'s "Keep the filename exactly as-is"), so a renamed or
    versioned copy correctly reports False here too.
    """
    folder = folder.strip()
    if not folder:
        return False
    return (Path(folder) / MASTER_LIST_FILENAME).is_file()


@st.dialog("Set up your shared master list")
def render_master_list_setup_dialog(current_names_dir: Path) -> None:
    """Render a modal prompting for the shared master-list folder."""
    st.write(
        "No names were found in the master list. If your team keeps a "
        f"shared copy of **{MASTER_LIST_FILENAME}** (e.g. in a Box folder), "
        "paste its folder path below to use it here - no restart needed."
    )
    st.caption(f"Currently reading from: `{current_names_dir}`")

    folder_input = st.text_input(
        "Folder containing the master list",
        placeholder=r"C:\Users\you\Box\Team\Master List Folder",
        key="master_list_setup_folder_input",
    )

    if folder_input.strip():
        if master_list_exists_at(folder_input):
            st.success(f"Found `{MASTER_LIST_FILENAME}` at this path.")
        else:
            st.warning(
                f"`{MASTER_LIST_FILENAME}` was not found at this exact path "
                "yet. Double-check it (or save anyway if the folder is "
                "still syncing in Box)."
            )

    col_save, col_skip = st.columns(2)
    with col_save:
        if st.button("Save and use this folder", type="primary", width="stretch"):
            if not folder_input.strip():
                st.error("Enter a folder path first.")
            else:
                save_master_list_dir(Path(folder_input.strip()))
                st.session_state.master_list_setup_dismissed = True
                st.rerun()
    with col_skip:
        if st.button("Skip for now", width="stretch"):
            st.session_state.master_list_setup_dismissed = True
            st.rerun()

    st.caption(
        "Don't have a shared folder? Skip this - names will still be "
        "pseudonymized, just with flagged auto-generated IDs instead of your "
        "team's curated ones. See `data/README.md` for the full manual setup "
        "steps (including the environment-variable alternative) if you'd "
        "rather use those instead."
    )
