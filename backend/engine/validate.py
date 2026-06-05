"""Validation orchestrator. Runs every rule and the schema check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .project import Project
from .rules import RULES
from .types import Issue, Location, Severity, ValidationReport

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "model"

SCHEMA_FILES: dict[str, str] = {
    "Can": "can.schema.json",
    "CanIf": "canif.schema.json",
    "CanTp": "cantp.schema.json",
    "PduR": "pdur.schema.json",
    "Com": "com.schema.json",
}


def _registry() -> Registry:
    shared = json.loads((MODEL_DIR / "shared" / "types.schema.json").read_text())
    resource = Resource(contents=shared, specification=DRAFT202012)
    return Registry().with_resource(uri=shared["$id"], resource=resource)


_REGISTRY = _registry()


def _schema(cls: str) -> dict[str, Any]:
    return json.loads((MODEL_DIR / SCHEMA_FILES[cls]).read_text())


def _validate_against_schema(cls: str, raw: dict[str, Any]) -> list[Issue]:
    validator = Draft202012Validator(_schema(cls), registry=_REGISTRY)
    issues: list[Issue] = []
    for err in validator.iter_errors(raw):
        path = tuple(err.absolute_path)
        issues.append(
            Issue(
                rule="schema.validates",
                severity=Severity.ERROR,
                message=err.message,
                location=Location(cls, path),
            )
        )
    return issues


def validate(project: Project) -> ValidationReport:
    """Run schema validation + every cross-file rule."""
    report = ValidationReport()

    # Schema validation (type, range, multiplicity, enum, required) is
    # the source of truth for single-document constraints.
    for cls, raw in project.raw.items():
        report.issues.extend(_validate_against_schema(cls, raw))

    # Cross-file rules.
    for rule in RULES:
        report.issues.extend(rule(project))

    return report
