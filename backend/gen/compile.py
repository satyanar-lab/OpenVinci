"""VERIFICATION LEVEL 1 — compile generated `*_Cfg.c` against vendor/as
BSW headers.

We run `gcc -c -fsyntax-only -Wall` (no object emitted, just parse +
typecheck) with `-I` paths covering every communication subsystem
under `vendor/as/infras/`. This catches:

- syntax errors in generated code,
- type mismatches with the BSW headers,
- missing struct fields the generator forgot to emit,
- missing includes.

It does NOT catch linker errors or runtime errors — those are
verification levels 2 and 3, on the roadmap.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .types import CompileMessage, CompileResult

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_AS = REPO_ROOT / "vendor" / "as"

# Hard ceiling per gcc invocation. The L1 syntax-only checks complete
# in well under a second locally; 30 s is comfortably above realistic
# variance while still preventing a malicious or runaway invocation
# from pinning the worker. Override with OPENVINCI_GCC_TIMEOUT_S for
# debugging if you ever need to.
GCC_TIMEOUT_S_DEFAULT = 30.0


def _gcc_timeout_s() -> float:
    raw = os.environ.get("OPENVINCI_GCC_TIMEOUT_S")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return GCC_TIMEOUT_S_DEFAULT

# Every BSW directory whose headers can show up in generated _Cfg
# includes. Listed explicitly (rather than auto-discovered) so
# upstream adding a new module doesn't silently change our include set.
_COMMUNICATION_SUBDIRS: tuple[str, ...] = (
    "CanIf",
    "CanTp",
    "Com",
    "ComM",
    "CanNm",
    "CanSM",
    "CanTSyn",
    "DoIP",
    "E2E",
    "J1939Tp",
    "LinIf",
    "LinTp",
    "Nm",
    "OsekNm",
    "PduR",
    "SecOC",
    "Sd",
    "SoAd",
    "TcpIp",
    "TLS",
    "UdpNm",
    "Xcp",
)

_DIAGNOSTIC_SUBDIRS: tuple[str, ...] = ("Dcm", "Dem", "Mirror")

_GCC_DIAG_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
    r"(?P<sev>error|warning|note):\s*(?P<msg>.*)$"
)


def include_dirs_for(staged_dir: Path) -> list[Path]:
    """Every -I path we need to compile a generated file."""
    base: list[Path] = [VENDOR_AS / "infras" / "include"]
    for sub in _COMMUNICATION_SUBDIRS:
        d = VENDOR_AS / "infras" / "communication" / sub
        if d.is_dir():
            base.append(d)
    for sub in _DIAGNOSTIC_SUBDIRS:
        d = VENDOR_AS / "infras" / "diagnostic" / sub
        if d.is_dir():
            base.append(d)
    # Every GEN dir inside the staged project — generated _Cfg.h files
    # find each other via these.
    for gen in sorted(staged_dir.rglob("GEN")):
        if gen.is_dir():
            base.append(gen)
    # Per-example include/ directory for tiny vendored shims (e.g.
    # cantp-iso15765 ships an empty Dcm_Cfg.h so the upstream PduR
    # generator's `#include "Dcm_Cfg.h"` resolves without us pulling
    # in the full vendor/as Dcm config tree). Convention: anything
    # named `include` inside an example tree is added to -I.
    for inc in sorted(staged_dir.rglob("include")):
        if inc.is_dir():
            base.append(inc)
    return base


def compile_check(staged_dir: Path, c_files: list[Path]) -> CompileResult:
    """Run gcc on each .c. Returns a CompileResult; status is `ok` iff
    every file compiled with zero errors (warnings are reported but
    do not change status)."""
    includes = include_dirs_for(Path(staged_dir))
    inc_flags: list[str] = []
    for d in includes:
        inc_flags.extend(["-I", str(d)])
    base_cmd = [
        "gcc",
        "-c",
        "-fsyntax-only",
        "-Wall",
        *inc_flags,
    ]

    messages: list[CompileMessage] = []
    any_error = False
    timeout_s = _gcc_timeout_s()

    for c_file in c_files:
        cmd = [*base_cmd, str(c_file)]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            # Treat a timeout as a real compile error so the API caller
            # sees it in their report rather than getting a 500 or a
            # hung connection. The error message is parseable enough
            # for the UI build-log to render.
            any_error = True
            messages.append(
                CompileMessage(
                    file=str(c_file),
                    line=None,
                    column=None,
                    severity="error",
                    message=(
                        f"gcc timed out after {timeout_s:.0f}s — aborted. "
                        f"Set OPENVINCI_GCC_TIMEOUT_S to override."
                    ),
                )
            )
            continue
        messages.extend(_parse_diagnostics(proc.stderr))
        if proc.returncode != 0:
            any_error = True
            # Make sure a non-zero exit always shows up as an error
            # even if gcc's stderr didn't match our regex.
            if not any(m.severity == "error" for m in messages if m.file.endswith(c_file.name)):
                messages.append(
                    CompileMessage(
                        file=str(c_file),
                        line=None,
                        column=None,
                        severity="error",
                        message=f"gcc exited {proc.returncode} without a parseable error",
                    )
                )

    return CompileResult(
        status="errors" if any_error else "ok",
        command=[*base_cmd, "<FILE>"],
        messages=messages,
    )


def _parse_diagnostics(stderr: str) -> list[CompileMessage]:
    out: list[CompileMessage] = []
    for line in stderr.splitlines():
        m = _GCC_DIAG_RE.match(line.strip())
        if not m:
            continue
        out.append(
            CompileMessage(
                file=m.group("file"),
                line=int(m.group("line")),
                column=int(m.group("col")) if m.group("col") else None,
                severity=m.group("sev"),  # type: ignore[arg-type]
                message=m.group("msg").strip(),
            )
        )
    return out
