"""OpenVinci validation + derivation engine.

Pure functions over the model layer (`app.model`). No FastAPI, no HTTP.
Designed so the same code drives the test suite, the CLI (when one
ships), and the future /validate, /derive, /solve HTTP endpoints.

Entry points:
    validate(project)               → ValidationReport
    apply_fix(project, fix)         → Project
    solve_all(project)              → (Project, list[Issue])
    derive_canif_pdus_from_com(...) → bucketed Rx/Tx entries
    derive_pdur_routines_from_com(...)
"""

from .derive import (
    derive_canif_pdu_for_com_message,
    derive_canif_pdus_from_com,
    derive_pdur_routine_for_com_message,
    derive_pdur_routines_from_com,
    derived_pdu_name,
    message_direction,
)
from .project import (
    Project,
    empty_project,
    load_project,
    project_from_raw,
)
from .rules import RULES
from .solve import SolveError, apply_fix, solve_all
from .types import Fix, Issue, Location, Severity, ValidationReport
from .validate import validate

__all__ = [
    "Fix",
    "Issue",
    "Location",
    "Project",
    "RULES",
    "Severity",
    "SolveError",
    "ValidationReport",
    "apply_fix",
    "derive_canif_pdu_for_com_message",
    "derive_canif_pdus_from_com",
    "derive_pdur_routine_for_com_message",
    "derive_pdur_routines_from_com",
    "derived_pdu_name",
    "empty_project",
    "load_project",
    "message_direction",
    "project_from_raw",
    "solve_all",
    "validate",
]
