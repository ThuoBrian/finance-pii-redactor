"""Case normalization to help spaCy detect ALL-CAPS names.

``en_core_web_lg`` is trained on ordinary mixed-case text and reliably fails to
tag fully-uppercase names (``MARY WANJIRU``). :func:`recase_uppercase` produces a
title-cased copy of the text that spaCy can recognize, used for a second
detection pass in :class:`PresidioEngine`.

The transform is **length-preserving**: ``str.capitalize()`` on an all-uppercase
alphabetic token returns a same-length string, so character offsets reported on
the recased copy map back exactly onto the original text.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"\w+", re.UNICODE)


def _recase_token(match: re.Match[str]) -> str:
    token = match.group()
    if len(token) >= 2 and token.isalpha() and token.isupper():
        return token.capitalize()
    return token


def recase_uppercase(text: str) -> str:
    """Title-case fully-uppercase alphabetic tokens, leaving everything else.

    Single-letter tokens (``I``), mixed-case words, and tokens containing digits
    or symbols are returned unchanged. The result has the same length as ``text``.
    """
    return _WORD.sub(_recase_token, text)
