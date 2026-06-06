"""DBC import + auto-wire.

`parse_dbc` is a pure mapping from cantools's parse tree to our Com
schema. `import_dbc_file` merges those messages into a Project's Com
network and then calls `auto_wire_from_com`, which uses the engine's
derivation functions to add the matching CanIf PDU, PduR routine, and
Can controller for each message. The output is a Project that
validates clean and is generate+compile ready.

Direction: vendor/as Com.py looks at `message.node == network.me` to
decide Tx vs Rx (see `engine/derive.py::message_direction`). The
importer respects that convention: it sets `message.node` to the DBC
sender; the caller's `me` parameter ends up on the Com network so the
direction is computed correctly downstream.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cantools

from app.model import CanConfig, CanIfConfig, ComConfig, PduRConfig, load
from engine import (
    Project,
    derive_canif_pdu_for_com_message,
    derive_pdur_routine_for_com_message,
    message_direction,
)


def parse_dbc(path: str | Path) -> list[dict[str, Any]]:
    """Parse a .dbc into a list of Com message dicts.

    The output shape matches `model/com.schema.json`'s Message $def.

    `cantools.database.Message.is_fd` is true when the DBC marks a frame
    as CAN FD (via the `BO_` VFrameFormat attribute / extended DBC).
    Lengths up to 64 are surfaced as-is — the schema accepts dlc<=64
    and the engine's `com.message-dlc-valid` rule enforces the FD vs
    classic length set. See docs/CANFD_FEASIBILITY.md §2.12 for why this
    matters at the importer boundary.
    """
    db = cantools.database.load_file(str(path))
    out: list[dict[str, Any]] = []
    for msg in db.messages:
        entry: dict[str, Any] = {
            "name": _identifier(msg.name),
            "id": f"0x{msg.frame_id:x}",
            "dlc": msg.length,
            "node": _identifier(msg.senders[0]) if msg.senders else "Unknown",
            "CycleTime": int(msg.cycle_time or 0),
            "signals": [_signal(sig) for sig in msg.signals],
        }
        if getattr(msg, "is_fd", False):
            entry["fd"] = True
        out.append(entry)
    return out


def import_dbc_file(
    dbc_path: str | Path,
    *,
    network_name: str,
    me: str,
    baudrate: int = 500000,
    device: str = "simulator_v2",
    port: int = 0,
    base_project: Project | None = None,
) -> Project:
    """Top-level entry: parse, merge into Com, then auto-wire.

    - `network_name` becomes the Com / CanIf / PduR / Can network name.
    - `me` is the ECU identity — direction depends on it.
    - `base_project` lets you import into an existing project; if None,
      a fresh project with Com+CanIf+PduR+Can is created.
    """
    messages = parse_dbc(dbc_path)
    project = base_project or _empty_project()
    _merge_messages_into_com(
        project,
        network_name=network_name,
        me=me,
        device=device,
        port=port,
        baudrate=baudrate,
        messages=messages,
    )
    return auto_wire_from_com(project, network_name=network_name)


def auto_wire_from_com(project: Project, *, network_name: str) -> Project:
    """For every Com message on `network_name`, ensure matching CanIf
    PDU + PduR routine + Can controller exist. Idempotent: re-runs are
    no-ops if nothing changed."""
    if not project.com:
        return project
    network = _find_com_network(project.com, network_name)
    if network is None or not network.messages:
        # No messages to wire; still ensure a Can controller exists.
        _ensure_can_controller(project, network_name)
        _refresh_models(project)
        return project

    _ensure_canif_network(project, network_name)
    _ensure_pdur_root(project)
    _ensure_can_controller(project, network_name)

    canif_net = _find_raw_canif_network(project, network_name)
    pdur_raw = project.raw["PduR"]
    existing_canif_names = {p["name"] for p in canif_net["RxPdus"] + canif_net["TxPdus"]}
    existing_pdur_names = {r["name"] for r in pdur_raw["routines"]}

    for msg in network.messages:
        direction = message_direction(msg, network)
        pdu_entry = derive_canif_pdu_for_com_message(msg, network)
        routine_entry = derive_pdur_routine_for_com_message(msg, network)

        if pdu_entry["name"] not in existing_canif_names:
            target = canif_net["TxPdus"] if direction == "Tx" else canif_net["RxPdus"]
            target.append(pdu_entry)
            existing_canif_names.add(pdu_entry["name"])

        if routine_entry["name"] not in existing_pdur_names:
            pdur_raw["routines"].append(routine_entry)
            existing_pdur_names.add(routine_entry["name"])

    _refresh_models(project)
    return project


# --- helpers ---------------------------------------------------------


def _identifier(s: str) -> str:
    """DBC names can include characters that are valid in DBC but not in
    C macros (we never get those in practice, but defensively coerce)."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in s)


def _signal(sig: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": _identifier(sig.name),
        "start": int(sig.start),
        "size": int(sig.length),
        "endian": "little" if sig.byte_order == "little_endian" else "big",
        "sign": "-" if sig.is_signed else "+",
    }
    # cantools normalises absent values to None; pass through only what's set.
    if sig.scale is not None and sig.scale != 1:
        out["factor"] = _num(sig.scale)
    if sig.offset is not None and sig.offset != 0:
        out["offset"] = _num(sig.offset)
    if sig.minimum is not None:
        out["min"] = _num(sig.minimum)
    if sig.maximum is not None:
        out["max"] = _num(sig.maximum)
    if sig.receivers:
        out["node"] = [_identifier(r) for r in sig.receivers]
    return out


def _num(x: float) -> int | float:
    # cantools returns Decimal sometimes; coerce to int when whole.
    f = float(x)
    return int(f) if f == int(f) else f


def _empty_project() -> Project:
    raw = {
        "Com": {"class": "Com", "networks": []},
        "CanIf": {"class": "CanIf", "networks": []},
        "PduR": {"class": "PduR", "routines": []},
        "Can": {"class": "Can", "controllers": []},
    }
    project = Project()
    project.raw = raw
    project.com = ComConfig.model_validate(raw["Com"])
    project.canif = CanIfConfig.model_validate(raw["CanIf"])
    project.pdur = PduRConfig.model_validate(raw["PduR"])
    project.can = CanConfig.model_validate(raw["Can"])
    return project


def _merge_messages_into_com(
    project: Project,
    *,
    network_name: str,
    me: str,
    device: str,
    port: int,
    baudrate: int,
    messages: list[dict[str, Any]],
) -> None:
    if "Com" not in project.raw:
        project.raw["Com"] = {"class": "Com", "networks": []}
    com_raw = project.raw["Com"]
    network_raw = _find_raw_network(com_raw, network_name)
    if network_raw is None:
        network_raw = {
            "name": network_name,
            "network": "CAN",
            "device": device,
            "port": port,
            "baudrate": baudrate,
            "me": me,
            "messages": [],
        }
        com_raw["networks"].append(network_raw)
    if "messages" not in network_raw:
        network_raw["messages"] = []

    existing = {m["name"] for m in network_raw["messages"]}
    for msg in messages:
        if msg["name"] not in existing:
            network_raw["messages"].append(msg)
            existing.add(msg["name"])
    # rebuild only the Com model; we'll do the full refresh after wiring.
    project.com = ComConfig.model_validate(com_raw)


def _ensure_canif_network(project: Project, network_name: str) -> None:
    if "CanIf" not in project.raw:
        project.raw["CanIf"] = {"class": "CanIf", "networks": []}
    canif_raw = project.raw["CanIf"]
    if _find_raw_network(canif_raw, network_name) is None:
        canif_raw["networks"].append(
            {"name": network_name, "RxPdus": [], "TxPdus": []}
        )


def _ensure_pdur_root(project: Project) -> None:
    if "PduR" not in project.raw:
        project.raw["PduR"] = {"class": "PduR", "routines": []}


def _ensure_can_controller(project: Project, network_name: str) -> None:
    if "Can" not in project.raw:
        project.raw["Can"] = {"class": "Can", "controllers": []}
    can_raw = project.raw["Can"]
    if any(c["name"] == network_name for c in can_raw["controllers"]):
        return
    can_raw["controllers"].append(
        {
            "name": network_name,
            "hwInstanceId": len(can_raw["controllers"]),
            "baudrate": 500000,
            "samplePoint": 75,
            "device": "simulator_v2",
        }
    )


def _refresh_models(project: Project) -> None:
    for cls in ("Com", "CanIf", "PduR", "Can"):
        if cls in project.raw:
            model = load(project.raw[cls])
            if cls == "Com":
                project.com = model
            elif cls == "CanIf":
                project.canif = model
            elif cls == "PduR":
                project.pdur = model
            elif cls == "Can":
                project.can = model


def _find_com_network(com, name: str):
    for net in com.networks:
        if net.name == name:
            return net
    return None


def _find_raw_network(module_raw: dict[str, Any], name: str) -> dict[str, Any] | None:
    for net in module_raw.get("networks", []):
        if net["name"] == name:
            return net
    return None


def _find_raw_canif_network(project: Project, name: str) -> dict[str, Any]:
    net = _find_raw_network(project.raw["CanIf"], name)
    assert net is not None, "ensure_canif_network should have created it"
    return net
