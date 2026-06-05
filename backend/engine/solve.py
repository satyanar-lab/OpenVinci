"""Solver — apply Fix objects to a Project and (optionally) iterate.

The Fix's per-module patch lists are RFC 6902 JSON Patches. We only
need the `add` op for our rules; the implementation is small enough
to keep in-tree rather than pulling in a dependency.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .project import Project, project_from_raw
from .types import Fix, Issue, Severity
from .validate import validate


class SolveError(ValueError):
    pass


def _split_pointer(pointer: str) -> list[str]:
    """RFC 6901 pointer → list of unescaped tokens."""
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise SolveError(f"non-root pointer must start with '/': {pointer!r}")
    return [tok.replace("~1", "/").replace("~0", "~") for tok in pointer[1:].split("/")]


def _apply_op(doc: Any, op: dict[str, Any]) -> Any:
    if op.get("op") != "add":
        raise SolveError(f"unsupported op: {op.get('op')!r}; only 'add' is implemented")
    tokens = _split_pointer(op["path"])
    if not tokens:
        return op["value"]
    *parent_tokens, last = tokens
    target = doc
    for tok in parent_tokens:
        target = _index(target, tok)
    if isinstance(target, list):
        if last == "-":
            target.append(op["value"])
        else:
            idx = int(last)
            target.insert(idx, op["value"])
    elif isinstance(target, dict):
        target[last] = op["value"]
    else:
        raise SolveError(f"cannot add into non-container at {op['path']!r}")
    return doc


def _index(container: Any, token: str) -> Any:
    if isinstance(container, list):
        return container[int(token)]
    if isinstance(container, dict):
        return container[token]
    raise SolveError(f"cannot descend into non-container with token {token!r}")


def apply_fix(project: Project, fix: Fix) -> Project:
    """Return a NEW Project with `fix` applied. The input is not mutated."""
    new_raw: dict[str, dict[str, Any]] = {
        cls: deepcopy(data) for cls, data in project.raw.items()
    }
    for cls, ops in fix.patches.items():
        # Allow a fix to create a module from scratch (e.g. add Can.json).
        if cls not in new_raw:
            raise SolveError(
                f"fix targets module {cls!r} but it isn't loaded in the project"
            )
        for op in ops:
            new_raw[cls] = _apply_op(new_raw[cls], op)
    return project_from_raw(new_raw)


def solve_all(project: Project, *, max_iterations: int = 25) -> tuple[Project, list[Issue]]:
    """Iteratively apply every available auto-fix until no more apply.

    Returns the resulting project and the list of issues that remained
    unfixable. Raises SolveError if the iteration cap is hit, which
    almost always means two rules disagree.
    """
    current = project
    seen_fix_keys: set[tuple[str, str]] = set()

    for _ in range(max_iterations):
        report = validate(current)
        fixable = [
            i
            for i in report.issues
            if i.fix is not None and i.severity is Severity.ERROR
        ]
        if not fixable:
            return current, report.issues

        # Apply each unique fix exactly once per pass; same fix coming
        # back means the rule re-fires for an unrelated row.
        applied_any = False
        for issue in fixable:
            assert issue.fix is not None
            key = (issue.rule, issue.fix.description)
            if key in seen_fix_keys:
                continue
            seen_fix_keys.add(key)
            current = apply_fix(current, issue.fix)
            applied_any = True
        if not applied_any:
            return current, report.issues

    raise SolveError(
        f"solver did not converge in {max_iterations} iterations — likely a rule loop"
    )
