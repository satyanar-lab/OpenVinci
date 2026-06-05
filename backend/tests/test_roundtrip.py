"""Round-trip fidelity tests.

For every real config under examples/canapp-min/ we:
  1. Read it as raw JSON (the ground truth).
  2. Parse it through the OpenVinci loader.
  3. Dump it back through the serializer.
  4. Assert structural equality with the original.

`dict == dict` in Python is order-independent on object keys and
order-sensitive on arrays — exactly the semantic JSON wants.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.model import (
    SUPPORTED_CLASSES,
    UnknownConfigClassError,
    dump,
    dump_to_path,
    load,
    load_from_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ROOT = REPO_ROOT / "examples" / "canapp-min" / "config"

EXAMPLES: dict[str, Path] = {
    "Can": EXAMPLE_ROOT / "Can" / "Can.json",
    "Com": EXAMPLE_ROOT / "Com" / "Com.json",
    "CanIf": EXAMPLE_ROOT / "Com" / "CanIf.json",
    "PduR": EXAMPLE_ROOT / "Com" / "PduR.json",
    "CanTp": EXAMPLE_ROOT / "CanTp" / "CanTp.json",
}


def _read_raw(path: Path) -> dict:
    return json.loads(path.read_text())


@pytest.mark.parametrize("cls_name,path", list(EXAMPLES.items()))
def test_roundtrip_structural_equality(cls_name: str, path: Path):
    raw = _read_raw(path)
    assert raw["class"] == cls_name, f"sanity: example must declare class:{cls_name!r}"

    model = load(raw)
    serialized = dump(model)

    assert serialized == raw, (
        f"round-trip broke fidelity for {cls_name}: "
        f"keys lost = {sorted(set(_flatten(raw)) - set(_flatten(serialized)))}; "
        f"keys gained = {sorted(set(_flatten(serialized)) - set(_flatten(raw)))}"
    )


def test_roundtrip_via_filesystem(tmp_path: Path):
    """Same proof but going through the on-disk loader+serializer."""
    src = EXAMPLES["Com"]
    raw = _read_raw(src)

    model = load_from_path(src)
    out = tmp_path / "Com.json"
    dump_to_path(model, out)

    assert json.loads(out.read_text()) == raw


def test_preserves_extra_keys_like_dash_name():
    """The real CanIf.json has `-name` / `-up` soft-comment aliases.

    These are not declared on the Pydantic model and must survive
    round-trip via `extra='allow'`. (docs/AUTOAS_NOTES.md notes the
    upstream uses these as commented-out alternatives.)
    """
    raw = _read_raw(EXAMPLES["CanIf"])
    found = [
        pdu
        for net in raw["networks"]
        for pdu in net["RxPdus"] + net["TxPdus"]
        if any(k.startswith("-") for k in pdu)
    ]
    assert found, "fixture sanity: at least one PDU should carry a dash-prefixed alias"

    serialized = dump(load(raw))
    serialized_found = [
        pdu
        for net in serialized["networks"]
        for pdu in net["RxPdus"] + net["TxPdus"]
        if any(k.startswith("-") for k in pdu)
    ]
    assert serialized_found == found


def test_preserves_pdur_backup_routines_block():
    """`backup-routines-secoc-test-over-cantp` is an undocumented top-level
    block in the real PduR.json. It must survive round-trip."""
    raw = _read_raw(EXAMPLES["PduR"])
    assert "backup-routines-secoc-test-over-cantp" in raw, "fixture sanity"
    serialized = dump(load(raw))
    assert (
        serialized["backup-routines-secoc-test-over-cantp"]
        == raw["backup-routines-secoc-test-over-cantp"]
    )


def test_preserves_cantp_backup_channels_block():
    raw = _read_raw(EXAMPLES["CanTp"])
    assert "backup-channels" in raw, "fixture sanity"
    serialized = dump(load(raw))
    assert serialized["backup-channels"] == raw["backup-channels"]


def test_unknown_class_rejected():
    with pytest.raises(UnknownConfigClassError):
        load({"class": "Bogus"})


def test_supported_classes_matches_examples():
    """Documentation safety net: the loader's dispatch table must cover
    every example we ship and vice versa."""
    assert set(SUPPORTED_CLASSES) == set(EXAMPLES)


def _flatten(obj, prefix: str = "") -> list[str]:
    """Yield 'dotted.key.paths' for every leaf in a nested JSON value."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_flatten(v, f"{prefix}[{i}]"))
    else:
        out.append(prefix)
    return out
