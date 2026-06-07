"""OpenVinci generation adapter (Layer 3).

Wraps vendor/as's code generators and runs VERIFICATION LEVEL 1 (gcc
`-c -fsyntax-only`) against the BSW headers. Pure Python + subprocess;
no FastAPI dependency. The HTTP layer in `app/main.py` calls
`generate_and_compile()` from here.

See docs/AUTOAS_NOTES.md §2 for the upstream generator API and §3 for
the host/PC build context this layer compiles against.
"""

from . import can_h7, ecu_glue
from .compile import VENDOR_AS, compile_check, include_dirs_for
from .generate import GENERATABLE_CLASSES, run_generators
from .pipeline import generate_and_compile
from .stage import stage_project
from .types import (
    CompileMessage,
    CompileResult,
    GeneratedFile,
    GenerateResult,
)

__all__ = [
    "CompileMessage",
    "CompileResult",
    "GENERATABLE_CLASSES",
    "GeneratedFile",
    "GenerateResult",
    "VENDOR_AS",
    "can_h7",
    "ecu_glue",
    "compile_check",
    "generate_and_compile",
    "include_dirs_for",
    "run_generators",
    "stage_project",
]
