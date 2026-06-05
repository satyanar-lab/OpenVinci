"""Project — bundle of loaded module models, indexed for fast lookups.

A project on disk is a directory with the layout vendor/as expects
(docs/AUTOAS_NOTES.md §1.1, docs/ARCHITECTURE.md §3.3):

    <root>/config/Can/Can.json
    <root>/config/Com/Com.json
    <root>/config/Com/CanIf.json
    <root>/config/Com/PduR.json
    <root>/config/CanTp/CanTp.json

Modules are optional; the engine treats absent modules as "not
configured" and skips rules that need them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.model import (
    CanConfig,
    CanIfConfig,
    CanTpConfig,
    ComConfig,
    PduRConfig,
    load,
)

CLASS_TO_PATH: dict[str, str] = {
    "Can": "config/Can/Can.json",
    "Com": "config/Com/Com.json",
    "CanIf": "config/Com/CanIf.json",
    "PduR": "config/Com/PduR.json",
    "CanTp": "config/CanTp/CanTp.json",
}


@dataclass
class Project:
    can: CanConfig | None = None
    canif: CanIfConfig | None = None
    cantp: CanTpConfig | None = None
    pdur: PduRConfig | None = None
    com: ComConfig | None = None
    raw: dict[str, dict[str, Any]] = field(default_factory=dict)
    # ^ raw[module] is the original parsed dict — solver patches it in
    #   place so the solver doesn't have to round-trip every model.

    # ---- indexed lookups (cheap helpers, used by many rules) ----

    def canif_pdu_names(self) -> set[str]:
        if not self.canif:
            return set()
        return {
            pdu.name
            for net in self.canif.networks
            for pdu in net.RxPdus + net.TxPdus
        }

    def canif_rx_pdu_names(self) -> set[str]:
        if not self.canif:
            return set()
        return {pdu.name for net in self.canif.networks for pdu in net.RxPdus}

    def canif_tx_pdu_names(self) -> set[str]:
        if not self.canif:
            return set()
        return {pdu.name for net in self.canif.networks for pdu in net.TxPdus}

    def canif_networks(self) -> set[str]:
        if not self.canif:
            return set()
        return {n.name for n in self.canif.networks}

    def can_controllers(self) -> set[str]:
        if not self.can:
            return set()
        return {c.name for c in self.can.controllers}

    def pdur_networks(self) -> set[str]:
        if not self.pdur or not self.pdur.networks:
            return set()
        return {n.name for n in self.pdur.networks}

    def com_networks(self) -> set[str]:
        if not self.com:
            return set()
        return {n.name for n in self.com.networks}

    def com_messages(self) -> Iterable[tuple[str, Any]]:
        """Yield (network_name, message) for every Com message."""
        if not self.com:
            return
        for net in self.com.networks:
            for msg in net.messages or []:
                yield net.name, msg

    def pdur_routine_names(self) -> set[str]:
        if not self.pdur:
            return set()
        return {r.name for r in self.pdur.routines}


def empty_project() -> Project:
    return Project()


def load_project(root: str | Path) -> Project:
    """Read every recognised module JSON under `root` into a Project.

    Missing files are simply absent on the result — this is not an
    error; it's how partial projects are represented.
    """
    root = Path(root)
    proj = Project()
    for cls, rel in CLASS_TO_PATH.items():
        path = root / rel
        if not path.is_file():
            continue
        raw = json.loads(path.read_text())
        proj.raw[cls] = raw
        model = load(raw)
        _attach(proj, cls, model)
    return proj


def project_from_raw(raw_by_class: dict[str, dict[str, Any]]) -> Project:
    """Build a Project from in-memory dicts, no filesystem.

    Used heavily by the engine tests so they can construct minimal
    fixtures in one expression."""
    proj = Project()
    for cls, data in raw_by_class.items():
        proj.raw[cls] = data
        _attach(proj, cls, load(data))
    return proj


def _attach(proj: Project, cls: str, model: Any) -> None:
    if cls == "Can":
        proj.can = model
    elif cls == "CanIf":
        proj.canif = model
    elif cls == "CanTp":
        proj.cantp = model
    elif cls == "PduR":
        proj.pdur = model
    elif cls == "Com":
        proj.com = model
    else:  # pragma: no cover — load() already rejects unknown classes
        raise ValueError(f"unsupported class: {cls}")
