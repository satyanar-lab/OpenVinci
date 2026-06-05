"""CanIf model.

Mirrors `vendor/as/tools/generator/CanIf.py` and the GUI schema at
`vendor/as/tools/json.editor/schema.json:544-589`. See
docs/AUTOAS_NOTES.md §1.2 "CanIf" for the canonical field tables.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import OpenVinciModel


class RxPdu(OpenVinciModel):
    name: str
    id: str
    hoh: int
    up: str
    mask: str | None = None


class TxPdu(OpenVinciModel):
    name: str
    id: str
    hoh: int
    up: str
    dynamic: bool | None = None


class CanIfNetwork(OpenVinciModel):
    name: str
    me: str | None = None
    dbc: str | None = None
    TxTimeout: int | None = None
    NumHth: int | None = None
    NumHrh: int | None = None
    ignore: list[str] | None = None
    E2E: list[str] | None = None
    RxPdus: list[RxPdu]
    TxPdus: list[TxPdu]


class CanIfConfig(OpenVinciModel):
    class_: Literal["CanIf"] = Field(alias="class")
    RxPacketPoolSize: int | None = None
    RxPacketDataSize: int | None = None
    TxPacketPoolSize: int | None = None
    TxPacketDataSize: int | None = None
    MainFunctionPeriod: int | None = None
    UsePostBuildConfig: bool | None = None
    UseTxCallout: bool | None = None
    UseRxCallout: bool | None = None
    networks: list[CanIfNetwork]
