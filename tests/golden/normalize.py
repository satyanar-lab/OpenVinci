"""Strip volatile timestamps from vendor/as generator output before diffing.

`vendor/as/tools/generator/helper.py::GenHeader` writes a header that
includes the current year and a `Generated at <ctime>` line. Neither
should make a golden snapshot drift — we replace both with stable
placeholders.
"""

from __future__ import annotations

import re

# Matches:  Copyright (C) 2021-YYYY Parai Wang <parai@foxmail.com>
_COPYRIGHT_RE = re.compile(
    rb"^( \* Copyright \(C\) 2021-)\d{4}( Parai Wang .*)$",
    flags=re.MULTILINE,
)

# Matches:  Generated at Fri Jun  5 19:42:15 2026
_GENERATED_AT_RE = re.compile(
    rb"^( \* Generated at ).+$",
    flags=re.MULTILINE,
)


def normalize_bytes(data: bytes) -> bytes:
    data = _COPYRIGHT_RE.sub(rb"\1<YEAR>\2", data)
    data = _GENERATED_AT_RE.sub(rb"\1<TIMESTAMP>", data)
    return data


def normalize_text(s: str) -> str:
    return normalize_bytes(s.encode()).decode()
