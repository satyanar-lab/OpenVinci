"""Structured types every engine rule returns.

These are pure dataclasses — no FastAPI / Pydantic dependency — so the
engine stays headless and trivially testable. The HTTP layer (Layer 3)
will serialize them; the React UI (Layer 4) will render them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Location:
    """Where an issue lives. Path is JSON-pointer-like (no leading slash).

    Example: Location("CanIf", ("networks", 0, "RxPdus", 2))
    points at the third Rx PDU of the first network in CanIf.json.
    """

    module: str  # "Can" | "CanIf" | "CanTp" | "PduR" | "Com"
    path: tuple[str | int, ...] = ()

    def json_pointer(self) -> str:
        """RFC 6901 pointer suitable for JSON Patch targets."""
        if not self.path:
            return ""
        out: list[str] = []
        for seg in self.path:
            s = str(seg).replace("~", "~0").replace("/", "~1")
            out.append(s)
        return "/" + "/".join(out)


@dataclass(frozen=True)
class Fix:
    """An auto-fix suggestion. Patches map module name → list of RFC 6902 ops.

    Splitting per module keeps each set of ops trivially applicable
    against the matching loaded model. `description` is one short line
    suitable for a UI button label.
    """

    description: str
    patches: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class Issue:
    rule: str  # stable id, e.g. "cantp.requires-canif-pdus"
    severity: Severity
    message: str
    location: Location
    fix: Fix | None = None


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def by_rule(self, rule: str) -> list[Issue]:
        return [i for i in self.issues if i.rule == rule]
