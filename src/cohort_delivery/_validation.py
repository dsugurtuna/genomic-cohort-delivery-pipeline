"""Shared input validation helpers."""

from __future__ import annotations

import re

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_identifier(value: str, label: str = "identifier") -> str:
    """Validate that an identifier is safe for use in filenames and paths."""
    if not value or ".." in value or not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"Invalid {label} {value!r}: must match [A-Za-z0-9][A-Za-z0-9._-]{{0,63}} "
            "without '..'"
        )
    return value
