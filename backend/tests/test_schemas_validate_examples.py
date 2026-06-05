"""Schema-vs-example consistency: every example must validate against
its schema, and vice versa the schemas must not over-constrain.

This is the strongest proof that `/model/*.schema.json` describes the
real autoas/as config format, not a sanitized version of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "model"
EXAMPLE_DIR = REPO_ROOT / "examples" / "canapp-min" / "config"

PAIRS: list[tuple[str, str, str]] = [
    # (class, schema filename, example path)
    ("Can", "can.schema.json", "Can/Can.json"),
    ("Com", "com.schema.json", "Com/Com.json"),
    ("CanIf", "canif.schema.json", "Com/CanIf.json"),
    ("PduR", "pdur.schema.json", "Com/PduR.json"),
    ("CanTp", "cantp.schema.json", "CanTp/CanTp.json"),
]


def _registry() -> Registry:
    """Resolve cross-schema $refs at validation time. Module schemas
    reference shared types via the shared schema's `$id`, so registering
    it under that URI is enough."""
    shared_path = MODEL_DIR / "shared" / "types.schema.json"
    shared = json.loads(shared_path.read_text())
    resource = Resource(contents=shared, specification=DRAFT202012)
    return Registry().with_resource(uri=shared["$id"], resource=resource)


@pytest.mark.parametrize("cls,schema_file,example_rel", PAIRS)
def test_schema_validates_real_example(cls: str, schema_file: str, example_rel: str):
    schema = json.loads((MODEL_DIR / schema_file).read_text())
    instance = json.loads((EXAMPLE_DIR / example_rel).read_text())
    validator = Draft202012Validator(schema, registry=_registry())
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    assert not errors, "\n".join(
        f"  - {list(e.path)}: {e.message}" for e in errors
    )


@pytest.mark.parametrize("schema_file", [p[1] for p in PAIRS])
def test_schema_is_well_formed_draft202012(schema_file: str):
    schema = json.loads((MODEL_DIR / schema_file).read_text())
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"].endswith("draft/2020-12/schema")
    assert "vendoredAsCommit" in schema, "every schema must record its source SHA"
