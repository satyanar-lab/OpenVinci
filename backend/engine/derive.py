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


def derived_pdu_name(message: Message, network: ComNetwork) -> str:
    """The PDU/routine name vendor/as's generators expect.

    Mirrors `vendor/as/tools/generator/Com.py` post() at lines 717-730,
    which auto-appends `_TX`/`_RX` to message names whose macroized
    form doesn't already contain "TX"/"RX", then network-prefixes
    everything. The combined name is what PduR and CanIf reference,
    so we have to compute the same string here for the auto-fix /
    auto-wire to produce links that resolve.

        STATUS (Tx)    → CAN0_STATUS_TX
        HEARTBEAT (Rx) → CAN0_HEARTBEAT_RX
        TX_MSG (Tx)    → CAN0_TX_MSG       (no suffix; name already has "TX")
        RX_MSG (Rx)    → CAN0_RX_MSG
    """
    direction = message_direction(message, network)
    base = message.name
    upper = base.upper()
    if direction == "Tx" and "TX" not in upper:
        base = f"{base}_TX"
    elif direction == "Rx" and "RX" not in upper:
        base = f"{base}_RX"
    return f"{network.name}_{base}"


def derive_canif_pdu_for_com_message(
    message: Message, network: ComNetwork, *, hoh: int = 0
) -> dict[str, Any]:
    """The CanIf PDU entry a Com message implies.

    `up` is "PduR" because Com messages reach CanIf through PduR
    routing.
    """
    return {
        "name": derived_pdu_name(message, network),
        "id": message.id,
        "hoh": hoh,
        "up": "PduR",
    }


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
