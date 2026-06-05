"""Project loader + indexed helpers."""

from __future__ import annotations

from pathlib import Path

from engine import load_project

from .fixtures import (
    can,
    canif,
    cantp,
    com,
    make_project,
    pdur,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_PROJECT = REPO_ROOT / "examples" / "canapp-min"


def test_load_real_canapp_min():
    p = load_project(EXAMPLE_PROJECT)
    assert p.can is not None
    assert p.canif is not None
    assert p.cantp is not None
    assert p.pdur is not None
    assert p.com is not None
    assert "CAN0" in p.com_networks()
    assert "CAN0" in p.canif_networks()


def test_load_partial_project_silently_omits_missing_modules(tmp_path: Path):
    (tmp_path / "config" / "Com").mkdir(parents=True)
    (tmp_path / "config" / "Com" / "Com.json").write_text(
        '{"class": "Com", "networks": [{"name": "CAN0", "network": "CAN", "me": "AS"}]}'
    )
    p = load_project(tmp_path)
    assert p.com is not None
    assert p.can is None and p.canif is None and p.cantp is None and p.pdur is None


def test_indexed_helpers_return_empty_when_module_absent():
    p = make_project()
    assert p.canif_pdu_names() == set()
    assert p.can_controllers() == set()
    assert p.pdur_routine_names() == set()
    assert list(p.com_messages()) == []


def test_canif_pdu_helpers_split_rx_and_tx():
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [
                        {"name": "P2P_RX", "id": "0x731", "hoh": 0, "up": "CanTp"}
                    ],
                    "TxPdus": [
                        {"name": "P2P_TX", "id": "0x732", "hoh": 0, "up": "CanTp"}
                    ],
                }
            ]
        )
    )
    assert p.canif_rx_pdu_names() == {"P2P_RX"}
    assert p.canif_tx_pdu_names() == {"P2P_TX"}
    assert p.canif_pdu_names() == {"P2P_RX", "P2P_TX"}


def test_com_messages_yields_per_network_pairs():
    p = make_project(
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [
                        {
                            "name": "MSG_A",
                            "id": "0x100",
                            "dlc": 8,
                            "node": "AS",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        }
                    ],
                }
            ]
        )
    )
    pairs = list(p.com_messages())
    assert len(pairs) == 1
    assert pairs[0][0] == "CAN0"
    assert pairs[0][1].name == "MSG_A"


def test_fixtures_assemble_full_project_round_trip_safe():
    p = make_project(
        can_=can(), canif_=canif(), cantp_=cantp(), pdur_=pdur(), com_=com()
    )
    assert set(p.raw) == {"Can", "CanIf", "CanTp", "PduR", "Com"}
