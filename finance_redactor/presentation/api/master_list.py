"""Master-list status, refresh and folder setup."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from finance_redactor.config import (
    master_list_setup_skipped,
    save_master_list_dir,
    set_master_list_setup_skipped,
)
from finance_redactor.presentation.api.context import Context
from finance_redactor.presentation.schemas import (
    FolderCheckOut,
    FolderIn,
    MasterListOut,
    QualityIssueOut,
    SetupIn,
)

MASTER_LIST_FILENAME = "Names List - Organized.xlsx"

router = APIRouter(prefix="/api/master-list", tags=["master-list"])


def master_list_exists_at(folder: str) -> bool:
    """Return True if ``folder`` holds the workbook under its exact filename.

    Matching is filename-exact (see ``data/README.md``), so a renamed or
    versioned copy reports False.
    """
    folder = folder.strip()
    if not folder:
        return False
    return (Path(folder) / MASTER_LIST_FILENAME).is_file()


def needs_setup(*, has_names: bool) -> bool:
    """Return True if the UI should offer the master-list setup.

    "Skip for now" is remembered across launches and forgotten as soon as a
    list loads with names, so a list that later goes missing prompts again.
    """
    skipped = master_list_setup_skipped()
    if has_names:
        if skipped:
            set_master_list_setup_skipped(False)
        return False
    return not skipped


@router.get("")
def status(context: Context) -> MasterListOut:
    """Return the master list's size, issues, age and setup state."""
    state = context.load_master_list()
    total = sum(state.counts.values())
    return MasterListOut(
        total=total,
        counts=dict(state.counts),
        issues=[
            QualityIssueOut(
                severity=i.severity,
                title=i.title,
                detail=i.detail,
                examples=list(i.examples),
                total=i.total,
            )
            for i in state.issues
        ],
        path=str(state.path),
        age_seconds=None if state.mtime is None else time.time() - state.mtime,
        needs_setup=needs_setup(has_names=total > 0),
    )


@router.post("/refresh")
def refresh(context: Context) -> MasterListOut:
    """Clear the cached master list, reload it and return its status."""
    context.refresh_master_list()
    return status(context)


@router.post("/check")
def check(body: FolderIn) -> FolderCheckOut:
    """Report whether the folder holds the master-list workbook."""
    return FolderCheckOut(found=master_list_exists_at(body.folder))


@router.post("/setup")
def setup(body: SetupIn, context: Context) -> MasterListOut:
    """Save the master-list folder; it applies on the next load."""
    folder = body.folder.strip()
    if not folder:
        raise HTTPException(422, "Enter a folder path first.")
    if not (master_list_exists_at(folder) or body.save_anyway):
        raise HTTPException(
            422, f"{MASTER_LIST_FILENAME} was not found in that folder."
        )
    save_master_list_dir(Path(folder))
    return status(context)


@router.post("/skip")
def skip(context: Context) -> MasterListOut:
    """Remember "Skip for now" across launches."""
    set_master_list_setup_skipped(True)
    return status(context)
