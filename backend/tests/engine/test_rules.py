"""One test (or pair) per rule.

Each rule has a stable id; we filter the report by id so an unrelated
rule firing won't fool the assertion. Every rule that produces an
auto-fix also gets a `solve_all`-applies-the-fix test in
test_solve.py.
"""

from __future__ import annotations

from engine import Severity, validate

from .fixtures import can, canif, cantp, com, make_project, pdur


# ----- helpers --------------------------------------------------------


def _issues(p, rule: str):
    return validate(p).by_rule(rule)


def _no_issues(p, rule: str):
    return not _issues(p, rule)


# ----- canif.network-has-can-controller -------------------------------


def test_canif_network_must_have_can_controller__clean():
    p = make_project(can_=can(), canif_=canif())  # both default to CAN0
    assert _no_issues(p, "canif.network-has-can-controller")


def test_canif_network_must_have_can_controller__missing():
    p = make_project(can_=can(controllers=[]), canif_=canif())
    issues = _issues(p, "canif.network-has-can-controller")
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR
    assert issues[0].fix is not None
    assert "Can" in issues[0].fix.patches


def test_canif_network_check_skipped_when_can_module_absent():
    p = make_project(canif_=canif())  # no Can configured at all
    assert _no_issues(p, "canif.network-has-can-controller")


# ----- pdur.network-has-canif-network ---------------------------------


def test_pdur_network_must_exist_in_canif__clean():
    p = make_project(
        canif_=canif(),
        pdur_=pdur(networks=[{"name": "CAN0", "network": "CAN", "me": "AS"}]),
    )
    assert _no_issues(p, "pdur.network-has-canif-network")


def test_pdur_network_must_exist_in_canif__missing():
    p = make_project(
        canif_=canif(),  # CAN0 only
        pdur_=pdur(networks=[{"name": "CAN9", "network": "CAN", "me": "AS"}]),
    )
    issues = _issues(p, "pdur.network-has-canif-network")
    assert len(issues) == 1
    fix = issues[0].fix
    assert fix is not None and "CanIf" in fix.patches
    assert fix.patches["CanIf"][0]["value"]["name"] == "CAN9"


# ----- com.network-has-canif-network ----------------------------------


def test_com_network_must_exist_in_canif__clean():
    p = make_project(canif_=canif(), com_=com())  # both CAN0
    assert _no_issues(p, "com.network-has-canif-network")


def test_com_network_must_exist_in_canif__missing():
    p = make_project(
        canif_=canif(networks=[{"name": "CAN0", "RxPdus": [], "TxPdus": []}]),
        com_=com(networks=[{"name": "CAN9", "network": "CAN", "me": "AS"}]),
    )
    issues = _issues(p, "com.network-has-canif-network")
    assert len(issues) == 1
    assert issues[0].fix is not None


# ----- canif.pdu-names-unique -----------------------------------------


def test_canif_pdu_names_globally_unique__clean():
    p = make_project(canif_=canif())  # empty PDUs
    assert _no_issues(p, "canif.pdu-names-unique")


def test_canif_pdu_names_globally_unique__duplicate_across_networks():
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [{"name": "DUP", "id": "0x1", "hoh": 0, "up": "CanTp"}],
                    "TxPdus": [],
                },
                {
                    "name": "CAN1",
                    "RxPdus": [],
                    "TxPdus": [{"name": "DUP", "id": "0x2", "hoh": 0, "up": "CanTp"}],
                },
            ]
        )
    )
    issues = _issues(p, "canif.pdu-names-unique")
    assert len(issues) == 1
    assert issues[0].fix is None  # collisions need a human decision


# ----- cantp.requires-canif-pdus --------------------------------------


def test_cantp_channel_requires_canif_pair__clean():
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
        ),
        cantp_=cantp(),  # channel P2P
    )
    assert _no_issues(p, "cantp.requires-canif-pdus")


def test_cantp_channel_requires_canif_pair__both_missing():
    p = make_project(canif_=canif(), cantp_=cantp())  # no PDUs at all
    issues = _issues(p, "cantp.requires-canif-pdus")
    assert len(issues) == 1
    fix = issues[0].fix
    assert fix is not None
    names = [op["value"]["name"] for op in fix.patches["CanIf"]]
    assert sorted(names) == ["P2P_RX", "P2P_TX"]


def test_cantp_channel_requires_canif_pair__one_missing():
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [
                        {"name": "P2P_RX", "id": "0x731", "hoh": 0, "up": "CanTp"}
                    ],
                    "TxPdus": [],
                }
            ]
        ),
        cantp_=cantp(),  # channel P2P, Tx PDU missing
    )
    issues = _issues(p, "cantp.requires-canif-pdus")
    assert len(issues) == 1
    names = [op["value"]["name"] for op in issues[0].fix.patches["CanIf"]]
    assert names == ["P2P_TX"]


# ----- pdur.endpoint-module-configured --------------------------------


def test_pdur_endpoint_module_must_be_configured__clean():
    p = make_project(
        canif_=canif(),
        cantp_=cantp(),
        pdur_=pdur(routines=[{"name": "P2P_RX", "from": "CanTp", "to": "CanIf"}]),
    )
    assert _no_issues(p, "pdur.endpoint-module-configured")


def test_pdur_endpoint_module_must_be_configured__missing_cantp_warning():
    p = make_project(
        canif_=canif(),
        pdur_=pdur(routines=[{"name": "P2P_RX", "from": "CanTp", "to": "CanIf"}]),
    )
    issues = _issues(p, "pdur.endpoint-module-configured")
    assert len(issues) == 1
    assert issues[0].severity is Severity.WARNING
    assert issues[0].fix is None


# ----- canif.up-module-configured -------------------------------------


def test_canif_up_module_user_callback_accepted():
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [
                        {
                            "name": "USER_RX",
                            "id": "0x123",
                            "hoh": 0,
                            "up": "UserAppRx",
                        }
                    ],
                    "TxPdus": [],
                }
            ]
        )
    )
    assert _no_issues(p, "canif.up-module-configured")


def test_canif_up_module_warns_when_referenced_module_missing():
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [
                        {"name": "P2P_RX", "id": "0x731", "hoh": 0, "up": "CanTp"}
                    ],
                    "TxPdus": [],
                }
            ]
        )
        # no CanTp configured
    )
    issues = _issues(p, "canif.up-module-configured")
    assert len(issues) == 1
    assert issues[0].severity is Severity.WARNING


def test_canif_up_module_silent_for_unmodeled_modules():
    """Routes into OsekNm / Xcp / SecOC are accepted silently — engine
    doesn't model them yet."""
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [
                        {"name": "OSEK_RX", "id": "0x400", "hoh": 0, "up": "OsekNm"}
                    ],
                    "TxPdus": [],
                }
            ]
        )
    )
    assert _no_issues(p, "canif.up-module-configured")


# ----- com.message-dlc-valid ------------------------------------------


def _com_msg(name: str, *, id_: str, dlc: int, fd: bool | None = None) -> dict:
    msg: dict = {
        "name": name,
        "id": id_,
        "dlc": dlc,
        "node": "AS",
        "signals": [{"name": f"sig_{name}", "start": 0, "size": 8, "endian": "little"}],
    }
    if fd is not None:
        msg["fd"] = fd
    return msg


def test_com_message_dlc_valid__classic_8_ok():
    p = make_project(
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [_com_msg("A", id_="0x100", dlc=8)],
                }
            ]
        )
    )
    assert _no_issues(p, "com.message-dlc-valid")


def test_com_message_dlc_valid__classic_over_8_flagged():
    p = make_project(
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [_com_msg("A", id_="0x100", dlc=16)],
                }
            ]
        )
    )
    issues = _issues(p, "com.message-dlc-valid")
    assert len(issues) == 1
    assert issues[0].severity is Severity.ERROR
    # The auto-fix should set fd: true so the engine can recover the
    # most common DBC-import shape (FD bit dropped, payload >8) without
    # the user having to hand-edit.
    fix = issues[0].fix
    assert fix is not None and "Com" in fix.patches
    patch = fix.patches["Com"][0]
    assert patch["op"] == "add"
    assert patch["path"].endswith("/fd")
    assert patch["value"] is True


def test_com_message_dlc_valid__fd_dlc_in_allowed_set():
    for dlc in (12, 16, 20, 24, 32, 48, 64):
        p = make_project(
            com_=com(
                networks=[
                    {
                        "name": "CAN0",
                        "network": "CANFD",
                        "me": "AS",
                        "messages": [_com_msg("A", id_="0x100", dlc=dlc, fd=True)],
                    }
                ]
            )
        )
        assert _no_issues(p, "com.message-dlc-valid"), f"dlc={dlc} should be valid"


def test_com_message_dlc_valid__fd_dlc_not_in_allowed_set():
    # 9 is illegal under both branches: too big for classic, not a valid FD size.
    p = make_project(
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CANFD",
                    "me": "AS",
                    "messages": [_com_msg("A", id_="0x100", dlc=9, fd=True)],
                }
            ]
        )
    )
    issues = _issues(p, "com.message-dlc-valid")
    assert len(issues) == 1
    # No auto-fix for an invalid FD size — the user has to round the
    # message up to the next legal size themselves.
    assert issues[0].fix is None


def test_com_message_dlc_valid__skipped_for_cantp_routed_message():
    """A Com message that PduR routes Com → CanTp is segmented across
    multiple CAN frames; its Com dlc reflects the unsegmented payload,
    not a single CAN frame size. The rule must defer to that."""
    p = make_project(
        canif_=canif(),
        cantp_=cantp(),
        pdur_=pdur(
            routines=[{"name": "CAN0_BIG_MSG_TX", "from": "Com", "to": "CanTp"}]
        ),
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [_com_msg("BIG_MSG", id_="0x500", dlc=32)],
                }
            ]
        ),
    )
    assert _no_issues(p, "com.message-dlc-valid")


def test_com_message_dlc_valid__skipped_when_secoc_intermediates_present():
    """SecOC wraps Com messages; the Com dlc and the on-wire CAN frame
    are decoupled. The rule defers when any unmodeled module sits in
    the route, matching the convention of com.message-has-canif-pdu."""
    p = make_project(
        canif_=canif(),
        pdur_=pdur(
            routines=[
                {"name": "CAN0_SECOC_MSG_TX", "from": "Com", "to": "SecOC"},
                {"name": "FW_CAN0_SECOC_MSG_TX", "from": "SecOC", "to": "CanIf"},
            ]
        ),
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [_com_msg("SECOC_MSG", id_="0x99", dlc=36)],
                }
            ]
        ),
    )
    assert _no_issues(p, "com.message-dlc-valid")


def test_com_message_dlc_valid__fd_under_8_still_ok():
    # FD frames may carry 0..8 bytes too; same length set as classic.
    p = make_project(
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CANFD",
                    "me": "AS",
                    "messages": [_com_msg("A", id_="0x100", dlc=4, fd=True)],
                }
            ]
        )
    )
    assert _no_issues(p, "com.message-dlc-valid")


# ----- com.message-id-unique-per-network ------------------------------


def test_com_message_ids_must_be_unique_per_network__clean():
    p = make_project(
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [
                        {
                            "name": "A",
                            "id": "0x100",
                            "dlc": 8,
                            "node": "AS",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        },
                        {
                            "name": "B",
                            "id": "0x101",
                            "dlc": 8,
                            "node": "AS",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        },
                    ],
                }
            ]
        )
    )
    assert _no_issues(p, "com.message-id-unique-per-network")


def test_com_message_ids_must_be_unique_per_network__collision():
    p = make_project(
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [
                        {
                            "name": "A",
                            "id": "0x100",
                            "dlc": 8,
                            "node": "AS",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        },
                        {
                            "name": "B",
                            "id": "0x100",
                            "dlc": 8,
                            "node": "AS",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        },
                    ],
                }
            ]
        )
    )
    assert len(_issues(p, "com.message-id-unique-per-network")) == 1


def test_com_message_ids_collision_across_networks_is_fine():
    """Same id on two different networks is OK."""
    p = make_project(
        canif_=canif(
            networks=[
                {"name": "CAN0", "RxPdus": [], "TxPdus": []},
                {"name": "CAN1", "RxPdus": [], "TxPdus": []},
            ]
        ),
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [
                        {
                            "name": "A",
                            "id": "0x100",
                            "dlc": 8,
                            "node": "AS",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        }
                    ],
                },
                {
                    "name": "CAN1",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [
                        {
                            "name": "B",
                            "id": "0x100",
                            "dlc": 8,
                            "node": "AS",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        }
                    ],
                },
            ]
        ),
    )
    assert _no_issues(p, "com.message-id-unique-per-network")


# ----- com.message-has-canif-pdu --------------------------------------


def test_com_tx_message_must_have_canif_tx_pdu__missing():
    p = make_project(
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
    issues = _issues(p, "com.message-has-canif-pdu")
    assert len(issues) == 1
    fix = issues[0].fix
    assert fix is not None
    op = fix.patches["CanIf"][0]
    assert op["path"].endswith("/TxPdus/-")
    assert op["value"] == {"name": "CAN0_TX_MSG", "id": "0x100", "hoh": 0, "up": "PduR"}


def test_com_rx_message_must_have_canif_rx_pdu__missing():
    p = make_project(
        canif_=canif(),
        com_=com(
            networks=[
                {
                    "name": "CAN0",
                    "network": "CAN",
                    "me": "AS",
                    "messages": [
                        {
                            "name": "RX_MSG",
                            "id": "0x101",
                            "dlc": 8,
                            "node": "Other",
                            "signals": [
                                {"name": "s", "start": 0, "size": 8, "endian": "little"}
                            ],
                        }
                    ],
                }
            ]
        ),
    )
    issues = _issues(p, "com.message-has-canif-pdu")
    assert len(issues) == 1
    op = issues[0].fix.patches["CanIf"][0]
    assert op["path"].endswith("/RxPdus/-")


def test_com_message_check_silent_when_canif_pdu_exists():
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [],
                    "TxPdus": [
                        {"name": "TX_MSG", "id": "0x100", "hoh": 0, "up": "PduR"}
                    ],
                }
            ]
        ),
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
    assert _no_issues(p, "com.message-has-canif-pdu")


# ----- pdur.routine-name-resolves -------------------------------------


def test_pdur_routine_naming_a_canif_pdu_must_match__clean():
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [
                        {"name": "P2P_RX", "id": "0x731", "hoh": 0, "up": "CanTp"}
                    ],
                    "TxPdus": [],
                }
            ]
        ),
        cantp_=cantp(),
        pdur_=pdur(routines=[{"name": "P2P_RX", "from": "CanTp", "to": "CanIf"}]),
    )
    assert _no_issues(p, "pdur.routine-name-resolves")


def test_pdur_routine_naming_a_canif_pdu_must_match__broken():
    p = make_project(
        canif_=canif(),  # no P2P_RX
        cantp_=cantp(),
        pdur_=pdur(routines=[{"name": "P2P_RX", "from": "CanTp", "to": "CanIf"}]),
    )
    issues = _issues(p, "pdur.routine-name-resolves")
    assert len(issues) == 1


def test_pdur_routine_to_secoc_is_silently_accepted():
    """Routines into modules the engine doesn't model are not flagged."""
    p = make_project(
        canif_=canif(
            networks=[
                {
                    "name": "CAN0",
                    "RxPdus": [],
                    "TxPdus": [
                        {"name": "FW_TX", "id": "0x99", "hoh": 0, "up": "SecOC"}
                    ],
                }
            ]
        ),
        pdur_=pdur(routines=[{"name": "FW_TX", "from": "SecOC", "to": "CanIf"}]),
    )
    assert _no_issues(p, "pdur.routine-name-resolves")


# ----- schema.validates -----------------------------------------------


def test_schema_validation_catches_bad_baudrate_range():
    """Pydantic accepts an int; the JSON Schema rejects baudrate < 1."""
    p = make_project(
        can_=can(
            controllers=[
                {
                    "name": "CAN0",
                    "hwInstanceId": 0,
                    "baudrate": 0,
                    "samplePoint": 75,
                    "device": "simulator_v2",
                }
            ]
        )
    )
    issues = _issues(p, "schema.validates")
    assert any("0" in i.message for i in issues)


# ----- aggregate ------------------------------------------------------


def test_clean_minimal_project_is_clean():
    p = make_project(can_=can(), canif_=canif())
    report = validate(p)
    assert report.ok


def test_real_example_project_validates_with_no_errors():
    """The bundled vendor/as example is the strongest possible smoke test."""
    from engine import load_project
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    p = load_project(repo_root / "examples" / "canapp-min")
    report = validate(p)
    # Warnings are allowed (e.g. routes into Dcm/SecOC referenced from PduR);
    # ERRORS are not.
    assert report.ok, [(i.rule, i.message) for i in report.errors]
