"""Excel read/write adapter (pandas + openpyxl).

Implements the :class:`ExcelGateway` port. Encapsulates all spreadsheet I/O,
including the yellow highlighting of changed cells, which previously lived in
the UI module.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Sequence
from io import BytesIO
from typing import Any, cast

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from finance_redactor.domain.errors import UnreadableFileError
from finance_redactor.infrastructure.documents import excel_formatting
from finance_redactor.infrastructure.documents.excel_formatting import SheetFormat

_HIGHLIGHT_FILL = PatternFill(fill_type="solid", fgColor="FFFF00")
_HEADER_FONT = Font(bold=True)
_CROSSWALK_SHEET_NAME = "Crosswalk"
_MAX_TITLE = 31  # Excel's limit on a sheet name
_INVALID_TITLE_CHARS = re.compile(r"[\[\]:*?/\\]")


class OpenpyxlExcelGateway:
    """Reads workbooks into DataFrames and writes highlighted redacted copies."""

    def read_sheets(self, source: object) -> dict[str, pd.DataFrame]:
        """Load every sheet of a workbook, in tab order, keyed by tab name.

        Hidden sheets are included: a hidden tab is still data.

        Raises :class:`UnreadableFileError` for a corrupted workbook or one
        renamed to ``.xlsx``/``.xls`` without really being one - openpyxl
        raises ``BadZipFile`` when the bytes aren't a zip at all, and
        ``KeyError`` when they're a zip but missing the xlsx package parts.
        """
        try:
            return pd.read_excel(source, sheet_name=None, engine="openpyxl")
        except (zipfile.BadZipFile, KeyError) as e:
            raise UnreadableFileError from e

    def read_formatting(self, source: object) -> dict[str, SheetFormat]:
        """Read each sheet's look (see :mod:`excel_formatting`), keyed by tab name.

        Best effort: formatting is a nicety, so a workbook openpyxl cannot
        fully load gives ``{}`` and a plain output rather than an error.
        """
        if hasattr(source, "seek"):
            source.seek(0)
        try:
            return excel_formatting.capture(load_workbook(cast(Any, source)))
        except Exception:  # noqa: BLE001 - any load failure just means no formatting
            return {}

    def text_columns(self, df: pd.DataFrame) -> list[str]:
        """Return free-text (string dtype) columns, used as the scan default.

        Uses ``pandas.api.types.is_string_dtype`` rather than checking
        ``dtype == object``: pandas 3.0 infers a dedicated string dtype
        (``StringDtype``, shown as ``str`` in ``df.dtypes``) for text columns
        read from Excel/CSV by default, not the legacy ``object`` dtype an
        `== object` check was written against - that check silently matched
        zero columns on pandas 3.0, so no column was ever pre-selected here.
        ``is_string_dtype`` matches both the new string dtype and legacy
        object-dtype string columns, while still excluding numeric/date
        columns and an all-null object column.
        """
        return [col for col in df.columns if pd.api.types.is_string_dtype(df[col])]

    def write(
        self,
        sheets: Sequence[tuple[str, pd.DataFrame, set[tuple[int, str]]]],
        crosswalk_df: pd.DataFrame | None,
        formats: Sequence[object | None] | None = None,
    ) -> bytes:
        """Serialize ``sheets`` to xlsx bytes, highlighting the given cells yellow.

        Each sheet is ``(tab name, data, highlighted (row, column) cells)``.
        Tab names are made valid for Excel (31 characters at most, none of the
        characters Excel forbids) and unique, so two tabs that were redacted to the same name both survive.
        ``crosswalk_df``, when given, is written as a final "Crosswalk" sheet.
        The app passes ``None``: the crosswalk holds real names, so it leaves
        as its own Confidential CSV and the workbook stays Internal. A source
        tab already called "Crosswalk" is still renamed, so the name stays
        free for the sheet.

        ``formats`` (one per sheet, in order; ``None`` for no formatting) is
        what :meth:`read_formatting` returned for the source tab, applied
        before the yellow highlight so the highlight wins on changed cells.
        """
        titles = _sheet_titles([name for name, _, _ in sheets])
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for title, (_, df, _) in zip(titles, sheets, strict=True):
                df.to_excel(writer, index=False, sheet_name=title)
            if crosswalk_df is not None:
                crosswalk_df.to_excel(
                    writer, index=False, sheet_name=_CROSSWALK_SHEET_NAME
                )
        buffer.seek(0)

        workbook = load_workbook(buffer)
        sheet_formats = list(formats) if formats is not None else [None] * len(sheets)
        for title, (_, df, highlighted_cells), fmt in zip(
            titles, sheets, sheet_formats, strict=True
        ):
            worksheet = workbook[title]
            for index, column in enumerate(df.columns, start=1):
                # pandas names a blank header cell "Unnamed: N"; don't write that.
                if re.fullmatch(r"Unnamed: \d+", str(column)):
                    worksheet.cell(row=1, column=index).value = None
            if isinstance(fmt, SheetFormat):
                excel_formatting.apply(worksheet, fmt, len(df), len(df.columns))
            col_index = {col: idx + 1 for idx, col in enumerate(df.columns)}
            for row_idx, col_name in highlighted_cells:
                if col_name in col_index:
                    # +2 accounts for the header row and 1-based indexing.
                    worksheet.cell(
                        row=row_idx + 2, column=col_index[col_name]
                    ).fill = _HIGHLIGHT_FILL

        if crosswalk_df is not None:
            for cell in workbook[_CROSSWALK_SHEET_NAME][1]:
                cell.font = _HEADER_FONT

        out = BytesIO()
        workbook.save(out)
        return out.getvalue()


def _sheet_titles(names: Sequence[str]) -> list[str]:
    """Return valid, unique Excel sheet titles for ``names``; "Crosswalk" is reserved."""
    taken = {_CROSSWALK_SHEET_NAME.lower()}
    titles: list[str] = []
    for position, name in enumerate(names, start=1):
        base = _INVALID_TITLE_CHARS.sub("_", name).strip().strip("'")[:_MAX_TITLE]
        base = base or f"Sheet{position}"
        title, attempt = base, 1
        while title.lower() in taken:
            attempt += 1
            suffix = f" ({attempt})"
            title = base[: _MAX_TITLE - len(suffix)] + suffix
        taken.add(title.lower())
        titles.append(title)
    return titles
