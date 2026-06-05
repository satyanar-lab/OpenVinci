"""CanTp model.

Mirrors `vendor/as/tools/generator/CanTp.py` and the GUI schema at
`vendor/as/tools/json.editor/schema.json:650-673`. See
docs/AUTOAS_NOTES.md §1.2 "CanTp".
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import OpenVinciModel


class CanTpChannel(OpenVinciModel):
    name: str
    AddressingFormat: Literal["STANDARD", "EXTENDED"] | None = None
    N_TA: str | None = None
    N_As: int | None = None
    N_Bs: int | None = None
    N_Cr: int | None = None
    STmin: int | None = None
    BS: int | None = None
    WftMax: int | None = None
    LL_DL: int | None = None
    # `padding` is `0x55` in the GUI default (a string) but ints are valid too.
    padding: int | str | None = None
    ComType: Literal["PHYSICAL", "FUNCTIONAL"] | None = None
    RxPduId: str | None = None
    TxPduId: str | None = None


class CanTpConfig(OpenVinciModel):
    class_: Literal["CanTp"] = Field(alias="class")
    UseTxConfirmation: bool | None = None
    UsePostBuildConfig: bool | None = None
    MainFunctionPeriod: int | None = None
    STMinAdjust: int | None = None
    zero_cost: str | None = None
    channels: list[CanTpChannel]
