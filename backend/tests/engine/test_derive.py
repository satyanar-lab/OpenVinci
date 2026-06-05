"""Derivation: Com messages → CanIf PDUs and PduR routines."""

from __future__ import annotations

from app.model.com import ComConfig

from engine import (
    derive_canif_pdu_for_com_message,
    derive_canif_pdus_from_com,
    derive_pdur_routine_for_com_message,
    derive_pdur_routines_from_com,
    message_direction,
)


def _com_network_with_messages():
    return ComConfig.model_validate(
        {
            "class": "Com",
            "networks": [
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [
                        {
                            "name": "TX_MSG",
                            "id": "0x100",
                            "dlc": 8,
                            "node": "AS",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        },
                        {
                            "name": "RX_MSG",
                            "id": "0x101",
                            "dlc": 8,
                            "node": "Other",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        },
                    ],
                }
            ],
        }
    ).networks[0]


def test_direction_is_tx_when_message_node_matches_me():
    network = _com_network_with_messages()
    assert message_direction(network.messages[0], network) == "Tx"


def test_direction_is_rx_otherwise():
    network = _com_network_with_messages()
    assert message_direction(network.messages[1], network) == "Rx"


def test_canif_pdu_derivation_for_tx_message():
    """Naming follows the upstream <NetName>_<MsgName> convention so the
    generated `COM_<net>_<msg>`, `CANIF_<pdu>`, and PduR's `COM_<routine>`
    / `CANIF_<routine>` macros all resolve to the same symbol."""
    network = _com_network_with_messages()
    pdu = derive_canif_pdu_for_com_message(network.messages[0], network)
    assert pdu == {"name": "CAN0_TX_MSG", "id": "0x100", "hoh": 0, "up": "PduR"}


def test_pdur_routine_tx_goes_com_to_canif():
    network = _com_network_with_messages()
    routine = derive_pdur_routine_for_com_message(network.messages[0], network)
    assert routine == {"name": "CAN0_TX_MSG", "from": "Com", "to": "CanIf"}


def test_pdur_routine_rx_goes_canif_to_com():
    network = _com_network_with_messages()
    routine = derive_pdur_routine_for_com_message(network.messages[1], network)
    assert routine == {"name": "CAN0_RX_MSG", "from": "CanIf", "to": "Com"}


def test_bulk_canif_derivation_buckets_correctly():
    network = _com_network_with_messages()
    bundles = derive_canif_pdus_from_com(network)
    assert [p["name"] for p in bundles["TxPdus"]] == ["CAN0_TX_MSG"]
    assert [p["name"] for p in bundles["RxPdus"]] == ["CAN0_RX_MSG"]


def test_bulk_pdur_derivation_emits_one_per_message():
    network = _com_network_with_messages()
    routines = derive_pdur_routines_from_com(network)
    assert [r["name"] for r in routines] == ["CAN0_TX_MSG", "CAN0_RX_MSG"]
    assert [r["from"] for r in routines] == ["Com", "CanIf"]


def test_derivation_on_empty_messages_yields_nothing():
    empty = ComConfig.model_validate(
        {
            "class": "Com",
            "networks": [{"name": "CAN0", "network": "CAN", "me": "AS"}],
        }
    ).networks[0]
    bundles = derive_canif_pdus_from_com(empty)
    assert bundles == {"RxPdus": [], "TxPdus": []}
    assert derive_pdur_routines_from_com(empty) == []
