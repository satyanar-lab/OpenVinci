"""Solver: apply individual fixes and iterate until convergence."""

from __future__ import annotations

import pytest

from engine import (
    Fix,
    SolveError,
    apply_fix,
    solve_all,
    validate,
)

from .fixtures import can, canif, cantp, com, make_project, pdur


# ----- apply_fix ------------------------------------------------------


def test_apply_fix_does_not_mutate_input():
    p = make_project(canif_=canif())
    fix = Fix(
        description="add Rx PDU",
        patches={
            "CanIf": [
                {
                    "op": "add",
                    "path": "/networks/0/RxPdus/-",
                    "value": {"name": "NEW_RX", "id": "0x999", "hoh": 0, "up": "CanTp"},
                }
            ]
        },
    )
    p2 = apply_fix(p, fix)
    assert "NEW_RX" not in p.canif_rx_pdu_names()
    assert "NEW_RX" in p2.canif_rx_pdu_names()


def test_apply_fix_rejects_unknown_target_module():
    p = make_project(canif_=canif())
    fix = Fix(description="x", patches={"Can": [{"op": "add", "path": "", "value": {}}]})
    with pytest.raises(SolveError, match="Can"):
        apply_fix(p, fix)


def test_apply_fix_rejects_non_add_ops():
    p = make_project(canif_=canif())
    fix = Fix(description="x", patches={"CanIf": [{"op": "remove", "path": "/networks/0"}]})
    with pytest.raises(SolveError, match="remove"):
        apply_fix(p, fix)


def test_apply_fix_inserts_at_index():
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [{"name": "A", "id": "0x1", "hoh": 0, "up": "CanTp"}],
                    "TxPdus": [],
                }
            ]
        )
    )
    fix = Fix(
        description="prepend B",
        patches={
            "CanIf": [
                {
                    "op": "add",
                    "path": "/networks/0/RxPdus/0",
                    "value": {"name": "B", "id": "0x2", "hoh": 0, "up": "CanTp"},
                }
            ]
        },
    )
    p2 = apply_fix(p, fix)
    assert [pdu.name for pdu in p2.canif.networks[0].RxPdus] == ["B", "A"]


# ----- solve_all ------------------------------------------------------


def test_solve_all_no_op_on_clean_project():
    p = make_project(can_=can(), canif_=canif())
    resolved, remaining = solve_all(p)
    assert validate(resolved).ok
    # remaining may carry warnings; errors must be zero.
    assert not [i for i in remaining if i.severity.value == "error"]


def test_solve_all_creates_missing_cantp_canif_pdus():
    p = make_project(can_=can(), canif_=canif(), cantp_=cantp())
    resolved, remaining = solve_all(p)
    names = resolved.canif_pdu_names()
    assert {"P2P_RX", "P2P_TX"} <= names
    assert validate(resolved).ok


def test_solve_all_creates_canif_pdu_for_com_message_and_then_can_controller():
    """Cascading fix: Com message missing CanIf entry → Solver adds it →
    CanIf network missing Can controller (still) → Solver adds that too."""
    p = make_project(
        can_=can(controllers=[]),  # empty Can — must be filled in
        canif_=canif(),
        com_=com(
            networks=[
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
                        }
                    ],
                }
            ]
        ),
    )
    resolved, remaining = solve_all(p)
    assert "CAN0" in resolved.can_controllers()
    assert "CAN0_TX_MSG" in resolved.canif_tx_pdu_names()
    assert validate(resolved).ok


def test_solve_all_passes_through_unfixable_warnings():
    """Schema-violating ranges are unfixable; engine must not loop forever."""
    p = make_project(
        canif_=canif(),
        # routine endpoint module not configured → warning, no fix
        pdur_=pdur(routines=[{"name": "P2P_RX", "from": "CanTp", "to": "CanIf"}]),
    )
    _resolved, remaining = solve_all(p)
    warnings = [i for i in remaining if i.severity.value == "warning"]
    assert any(i.rule == "pdur.endpoint-module-configured" for i in warnings)


def test_solve_all_converges_on_real_example():
    """Sanity: real vendor/as example must solve without hitting the cap."""
    from engine import load_project
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    p = load_project(repo_root / "examples" / "canapp-min")
    resolved, _ = solve_all(p)
    assert validate(resolved).ok
