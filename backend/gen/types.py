"""Wire types returned by the gen layer. Plain dataclasses so the
HTTP layer can `asdict()` them and ship the JSON straight to the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class GeneratedFile:
    path: str  # repo-relative when surfaced to the API
    module: str  # the "class" key (Com / CanIf / …)
    size_bytes: int


@dataclass(frozen=True)
class CompileMessage:
    file: str  # repo-relative source path
    line: int | None
    column: int | None
    severity: Literal["error", "warning", "note"]
    message: str


@dataclass
class CompileResult:
    # "ok"          — every file compiled with zero errors.
    # "errors"      — at least one gcc invocation reported an error.
    # "unavailable" — gcc isn't on PATH, so verification was skipped.
    #                 The desktop launcher and any clean-machine
    #                 install MUST reach this state cleanly rather
    #                 than throwing a 500: generation itself doesn't
    #                 need the C toolchain — only this compile-check
    #                 step does.
    status: Literal["ok", "errors", "unavailable"]
    command: list[str]  # representative gcc command (with <FILE> placeholder)
    messages: list[CompileMessage] = field(default_factory=list)

    @property
    def errors(self) -> list[CompileMessage]:
        return [m for m in self.messages if m.severity == "error"]

    @property
    def warnings(self) -> list[CompileMessage]:
        return [m for m in self.messages if m.severity == "warning"]


@dataclass
class GenerateResult:
    files: list[GeneratedFile] = field(default_factory=list)
    compile_result: CompileResult | None = None
