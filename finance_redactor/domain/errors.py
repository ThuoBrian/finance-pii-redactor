"""Errors raised by the redaction flows for the UI to turn into a message.

These live in ``domain`` because the infrastructure gateways that raise them
and the presentation flows that catch them both already depend on ``domain``
and on nothing of each other's - putting the type here shares it without
adding an infrastructure -> application import edge that no other adapter
needs.

Deliberately carry no detail about the file that triggered them: the message
a user sees is written at the presentation layer, so nothing here can end up
echoing a filename or document content into a traceback.
"""

from __future__ import annotations


class EncryptedPdfError(Exception):
    """A PDF needs a password before any of its pages can be read."""


class UnreadableFileError(Exception):
    """A file could not be parsed as the format its extension promised.

    Covers a corrupted file, one renamed to the wrong extension, or one
    whose underlying zip/package structure is truncated or invalid - the
    three gateways each raise this for their own format's version of "this
    isn't really a workbook/document/PDF", so the presentation layer has one
    error to catch instead of three different parser libraries' exception
    types.
    """
