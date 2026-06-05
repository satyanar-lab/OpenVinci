"""Can — OpenVinci-only schema for the low-level CAN driver.

Upstream has no `class: "Can"` generator; the driver config is hand
written C (`vendor/as/app/platform/simulator/src/config/Can_Cfg.c`).
Fields here mirror `Can_ChannelConfigType` so an emitter can be added
later. See docs/AUTOAS_NOTES.md §1.2 "Can".
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import OpenVinciModel


class CanController(OpenVinciModel):
    name: str
    hwInstanceId: int
    baudrate: int = 500000
    samplePoint: int | None = None
    device: str


class CanConfig(OpenVinciModel):
    class_: Literal["Can"] = Field(alias="class")
    controllers: list[CanController]
