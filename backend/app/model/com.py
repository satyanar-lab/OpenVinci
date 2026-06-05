"""Com model.

Mirrors `vendor/as/tools/generator/Com.py:11-100` and the GUI schema at
`vendor/as/tools/json.editor/schema.json:715-739+`. See
docs/AUTOAS_NOTES.md §1.2 "Com". The upstream-typo fields
`enable_message_rx_notificaiton` and
`enable_message_rx_timeout_notificaiton` are kept verbatim.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .common import OpenVinciModel


class Signal(OpenVinciModel):
    name: str
    start: int
    size: int
    endian: Literal["big", "little"]
    sign: Literal["+", "-"] | None = None
    # InitialValue can be a number, a Python expression string
    # (e.g. "[i for i in range(32)]"), or an array.
    InitialValue: Any | None = None
    factor: int | float | None = None
    offset: int | float | None = None
    min: int | float | None = None
    max: int | float | None = None
    node: str | list[str] | None = None
    isGroup: bool | None = None
    group: str | None = None
    InvalidNotification: str | None = None
    RxNotification: str | None = None
    RxTOut: str | None = None
    FirstTimeout: int | None = None
    Timeout: int | None = None
    DataInvalidAction: str | None = None
    RxDataTimeoutAction: str | None = None
    ErrorNotification: str | None = None
    TxNotification: str | None = None


class Message(OpenVinciModel):
    name: str
    id: str
    dlc: int
    node: str
    CycleTime: int | None = None
    signals: list[Signal]


class E2EBinding(OpenVinciModel):
    name: str
    profile: str


class ComNetwork(OpenVinciModel):
    name: str
    network: Literal["CAN", "CANFD", "LIN"]
    device: str | None = None
    port: int | None = None
    baudrate: int | None = None
    me: str
    use_dbc: bool | None = None
    dbc: str | None = None
    use_ldf: bool | None = None
    ldf: str | None = None
    timeout_factor: int | None = None
    enable_message_tx_callout: bool | None = None
    enable_message_rx_callout: bool | None = None
    enable_message_rx_notificaiton: bool | None = None  # sic — upstream spelling
    enable_signal_rx_notification: bool | None = None
    enable_message_rx_timeout_notificaiton: bool | None = None  # sic
    enable_signal_rx_timeout_notification: bool | None = None
    trigger: list[str] | None = None
    # `groups` is a list of single-key dicts: {<groupName>: [<sigName>, ...]}
    groups: list[dict[str, list[str]]] | None = None
    messages: list[Message] | None = None
    E2E: list[E2EBinding] | None = None


class ComConfig(OpenVinciModel):
    class_: Literal["Com"] = Field(alias="class")
    E2E: str | None = None
    nodes: list[str] | None = None
    group_signals: list[str] | None = None
    networks: list[ComNetwork]
