"""Derivation — pure functions that compute the entries Layer-3
generators expect from higher-level Com declarations.

The two main derivations:
1. For each Com message, produce the CanIf PDU entry that should
   reference it (RxPdus[] or TxPdus[] depending on direction).
2. For each Com message, produce the PduR routine that connects it
   end-to-end with CanIf.

Direction follows vendor/as Com.py convention: if `message.node ==
network.me`, this ECU produces the message ⇒ Tx; otherwise Rx.
"""

from __future__ import annotations

from typing import Any, Literal

from app.model.com import ComNetwork, Message

Direction = Literal["Tx", "Rx"]


def message_direction(message: Message, network: ComNetwork) -> Direction:
    return "Tx" if message.node == network.me else "Rx"


# Vendor/as substitutes a small set of well-known abbreviations after the
# CamelCase split — match `vendor/as/tools/generator/helper.py::toMacro`.
_MACRO_SUBS: tuple[tuple[str, str], ...] = (
    ("CAN_TP", "CANTP"),
    ("LIN_TP", "LINTP"),
    ("PDU_R", "PDUR"),
    ("CAN_IF", "CANIF"),
    ("__", "_"),
)


def to_macro(s: str) -> str:
    """Port of `vendor/as/tools/generator/helper.py::toMacro`.

    Splits CamelCase / acronym boundaries into `UPPER_SNAKE_CASE` and
    applies the same abbreviation substitutions. Used by Com.py when
    emitting `COM_<net>_<msg>` macros — if we don't apply the same
    transformation here, PduR's `COM_<routine_name>` references won't
    resolve against the symbols Com defines.

        ExampleMessage  → EXAMPLE_MESSAGE
        TX_MSG          → TX_MSG       (already in macro form)
        CAN0            → CAN0
        Foo_RX          → FOO_RX
    """
    if not s:
        return s
    words: list[str] = []
    word: str | None = None
    for ch in s:
        if ch.isupper() or ch.isdigit():
            if word is not None:
                last = word[-1]
                concat = (
                    (last.isupper() and ch.islower())
                    or (last.isupper() and ch.isupper())
                    or (last.islower() and ch.islower())
                    or (last.isdigit() and ch.isdigit())
                    or (last.isupper() and ch.isdigit())
                    or (last.isdigit() and ch.isupper())
                )
                if concat:
                    word += ch
                    continue
                words.append(word)
            word = ch
        else:
            word = ch if word is None else word + ch
    if word is not None:
        words.append(word)
    out = "_".join(w.upper() for w in words)
    for old, new in _MACRO_SUBS:
        out = out.replace(old, new)
    return out


def derived_pdu_name(message: Message, network: ComNetwork) -> str:
    """The PDU/routine name vendor/as's generators expect.

    Mirrors `vendor/as/tools/generator/Com.py::post()` (which appends
    `_TX`/`_RX` to message names whose macroized form lacks them, then
    network-prefixes everything) AND `helper.py::toMacro` (which
    splits CamelCase into UPPER_SNAKE before macro emission). The
    routine and CanIf-PDU name has to be in this macro form so PduR's
    `COM_<routine_name>` references resolve cleanly against Com's
    `COM_<net>_<toMacro(msg)>_<TX|RX>`.

        STATUS         (Tx) → CAN0_STATUS_TX
        ExampleMessage (Rx) → CAN0_EXAMPLE_MESSAGE_RX
        TX_MSG         (Tx) → CAN0_TX_MSG       (already in macro form)
        Foo_RX         (Rx) → CAN0_FOO_RX       (already has _RX)
    """
    direction = message_direction(message, network)
    macro = to_macro(message.name)
    if direction == "Tx" and "TX" not in macro:
        macro = f"{macro}_TX"
    elif direction == "Rx" and "RX" not in macro:
        macro = f"{macro}_RX"
    return f"{network.name}_{macro}"


def derive_canif_pdu_for_com_message(
    message: Message, network: ComNetwork, *, hoh: int = 0
) -> dict[str, Any]:
    """The CanIf PDU entry a Com message implies.

    `up` is "PduR" because Com messages reach CanIf through PduR
    routing.

    The `fd` flag is carried through when set on the Com message so the
    CanIf entry reflects the same frame format the importer derived
    from the DBC.
    """
    entry: dict[str, Any] = {
        "name": derived_pdu_name(message, network),
        "id": message.id,
        "hoh": hoh,
        "up": "PduR",
    }
    if message.fd:
        entry["fd"] = True
    return entry


def derive_pdur_routine_for_com_message(
    message: Message, network: ComNetwork
) -> dict[str, Any]:
    """The PduR routine that connects Com ⇄ CanIf for one message."""
    direction = message_direction(message, network)
    name = derived_pdu_name(message, network)
    if direction == "Tx":
        return {"name": name, "from": "Com", "to": "CanIf"}
    return {"name": name, "from": "CanIf", "to": "Com"}


def derive_canif_pdus_from_com(network: ComNetwork) -> dict[str, list[dict[str, Any]]]:
    """Bulk: every Com message on a network → CanIf PDU entry, bucketed."""
    rx: list[dict[str, Any]] = []
    tx: list[dict[str, Any]] = []
    for msg in network.messages or []:
        entry = derive_canif_pdu_for_com_message(msg, network)
        if message_direction(msg, network) == "Tx":
            tx.append(entry)
        else:
            rx.append(entry)
    return {"RxPdus": rx, "TxPdus": tx}


def derive_pdur_routines_from_com(network: ComNetwork) -> list[dict[str, Any]]:
    """Bulk: every Com message on a network → PduR routine entry."""
    return [
        derive_pdur_routine_for_com_message(msg, network)
        for msg in network.messages or []
    ]
