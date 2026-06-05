"""PduR model.

Mirrors `vendor/as/tools/generator/PduR.py:25-80` and the GUI schema at
`vendor/as/tools/json.editor/schema.json:609-648`. The `from` Python
keyword is aliased; `populate_by_name=True` lets construction from
either name work, and `by_alias=True` writes back the upstream key.
See docs/AUTOAS_NOTES.md §1.2 "PduR".
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import OpenVinciModel


class Destination(OpenVinciModel):
    name: str
    to: str
    fake: str | None = None


class Routine(OpenVinciModel):
    name: str
    from_: str = Field(alias="from")
    to: str
    dest: str | None = None
    fake: str | None = None
    comments: str | None = None
    destinations: list[Destination] | None = None


class PduRNetwork(OpenVinciModel):
    name: str
    network: Literal["CAN", "CANFD", "LIN"]
    me: str | None = None
    dbc: str | None = None
    ignore: list[str] | None = None


class PduRMemory(OpenVinciModel):
    name: str
    size: int
    number: int


class PduRConfig(OpenVinciModel):
    class_: Literal["PduR"] = Field(alias="class")
    routines: list[Routine]
    networks: list[PduRNetwork] | None = None
    memory: list[PduRMemory] | None = None
