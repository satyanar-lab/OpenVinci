"""Small factory functions that build raw module dicts.

Each factory returns the minimal valid JSON dict for its module. Tests
override specific fields by passing kwargs.
"""

from __future__ import annotations

from typing import Any

from engine import Project, project_from_raw


def can(*, controllers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "class": "Can",
        "controllers": controllers
        if controllers is not None
        else [
            {
                "name": "CAN0",
                "hwInstanceId": 0,
                "baudrate": 500000,
                "samplePoint": 75,
                "device": "simulator_v2",
            }
        ],
    }


def canif(*, networks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "class": "CanIf",
        "networks": networks
        if networks is not None
        else [{"name": "CAN0", "RxPdus": [], "TxPdus": []}],
    }


def cantp(*, channels: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "class": "CanTp",
        "channels": channels if channels is not None else [{"name": "P2P"}],
    }


def pdur(
    *,
    routines: list[dict[str, Any]] | None = None,
    networks: list[dict[str, Any]] | None = None,
    memory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "class": "PduR",
        "routines": routines if routines is not None else [],
    }
    if networks is not None:
        out["networks"] = networks
    if memory is not None:
        out["memory"] = memory
    return out


def com(*, networks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "class": "Com",
        "networks": networks
        if networks is not None
        else [{"name": "CAN0", "network": "CAN", "me": "AS"}],
    }


def make_project(
    *,
    can_: dict[str, Any] | None = None,
    canif_: dict[str, Any] | None = None,
    cantp_: dict[str, Any] | None = None,
    pdur_: dict[str, Any] | None = None,
    com_: dict[str, Any] | None = None,
) -> Project:
    raw: dict[str, dict[str, Any]] = {}
    if can_ is not None:
        raw["Can"] = can_
    if canif_ is not None:
        raw["CanIf"] = canif_
    if cantp_ is not None:
        raw["CanTp"] = cantp_
    if pdur_ is not None:
        raw["PduR"] = pdur_
    if com_ is not None:
        raw["Com"] = com_
    return project_from_raw(raw)
