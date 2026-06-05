"""All engine rules.

Each rule is a small generator function that takes a Project and yields
Issue objects. Rules are pure and composable; the orchestrator in
validate.py just calls every entry in RULES.

Rule IDs are stable strings ("group.short-name") suitable for
suppression rules, UI filtering, and documentation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .derive import (
    derive_canif_pdu_for_com_message,
    derived_pdu_name,
    message_direction,
)
from .project import Project
from .types import Fix, Issue, Location, Severity

Rule = Callable[[Project], Iterable[Issue]]

RULES: list[Rule] = []

# Modules the engine fully models. Reference-integrity rules apply when
# both endpoints of a route are in this set; otherwise the route may
# involve an upstream-supported but engine-unmodeled module (SecOC,
# Mirror, Csm, E2E, J1939Tp, DoIP, Dcm, …) and we can't make assertions
# about names or wiring.
MODELED_MODULES: frozenset[str] = frozenset({"Can", "CanIf", "CanTp", "PduR", "Com"})


def _rule(func: Rule) -> Rule:
    RULES.append(func)
    return func


def _has_unmodeled_intermediates(project: Project) -> bool:
    """True if PduR or CanIf reference any module the engine doesn't model.

    Configs that route Com through SecOC / Mirror / etc. legitimately
    rename PDUs at each hop, so rules that assume `Com message name ==
    CanIf PDU name` would false-positive. We back off rather than guess.
    """
    if project.pdur:
        for r in project.pdur.routines:
            if r.from_ not in MODELED_MODULES or r.to not in MODELED_MODULES:
                return True
    if project.canif:
        for net in project.canif.networks:
            for pdu in net.RxPdus + net.TxPdus:
                if pdu.up.startswith("User"):
                    continue
                # Modules CanIf may legally hand to that engine doesn't model.
                if pdu.up in {"OsekNm", "CanNm", "Xcp", "CanTSyn"}:
                    continue
                if pdu.up not in MODELED_MODULES:
                    return True
    return False


# ----- helpers --------------------------------------------------------


def _canif_network_index(project: Project, name: str) -> int | None:
    if not project.canif:
        return None
    for i, net in enumerate(project.canif.networks):
        if net.name == name:
            return i
    return None


def _patch_add(path: str, value: Any) -> dict[str, Any]:
    """RFC 6902 add op."""
    return {"op": "add", "path": path, "value": value}


# ----- reference-integrity rules --------------------------------------


@_rule
def canif_network_has_can_controller(project: Project) -> Iterable[Issue]:
    """Every CanIf network needs a Can controller of the same name."""
    if not project.canif or not project.can:
        return
    controllers = project.can_controllers()
    for i, net in enumerate(project.canif.networks):
        if net.name in controllers:
            continue
        new_controller = {
            "name": net.name,
            "hwInstanceId": len(project.can.controllers),
            "baudrate": 500000,
            "samplePoint": 75,
            "device": "simulator_v2",
        }
        yield Issue(
            rule="canif.network-has-can-controller",
            severity=Severity.ERROR,
            message=(
                f"CanIf network {net.name!r} has no matching Can controller. "
                f"Configured controllers: {sorted(controllers) or 'none'}."
            ),
            location=Location("CanIf", ("networks", i)),
            fix=Fix(
                description=f"Add Can controller {net.name!r}",
                patches={"Can": [_patch_add("/controllers/-", new_controller)]},
            ),
        )


@_rule
def pdur_network_has_canif_network(project: Project) -> Iterable[Issue]:
    """Every PduR network must be configured in CanIf."""
    if not project.pdur or not project.canif or not project.pdur.networks:
        return
    canif_names = project.canif_networks()
    for i, net in enumerate(project.pdur.networks):
        if net.name in canif_names:
            continue
        yield Issue(
            rule="pdur.network-has-canif-network",
            severity=Severity.ERROR,
            message=(
                f"PduR network {net.name!r} is not declared in CanIf. "
                f"Configured CanIf networks: {sorted(canif_names) or 'none'}."
            ),
            location=Location("PduR", ("networks", i)),
            fix=Fix(
                description=f"Add CanIf network {net.name!r}",
                patches={
                    "CanIf": [
                        _patch_add(
                            "/networks/-",
                            {"name": net.name, "RxPdus": [], "TxPdus": []},
                        )
                    ]
                },
            ),
        )


@_rule
def com_network_has_canif_network(project: Project) -> Iterable[Issue]:
    """Every Com network must be configured in CanIf."""
    if not project.com or not project.canif:
        return
    canif_names = project.canif_networks()
    for i, net in enumerate(project.com.networks):
        if net.name in canif_names:
            continue
        yield Issue(
            rule="com.network-has-canif-network",
            severity=Severity.ERROR,
            message=(
                f"Com network {net.name!r} is not declared in CanIf. "
                f"Configured CanIf networks: {sorted(canif_names) or 'none'}."
            ),
            location=Location("Com", ("networks", i)),
            fix=Fix(
                description=f"Add CanIf network {net.name!r}",
                patches={
                    "CanIf": [
                        _patch_add(
                            "/networks/-",
                            {"name": net.name, "RxPdus": [], "TxPdus": []},
                        )
                    ]
                },
            ),
        )


@_rule
def canif_pdu_names_unique(project: Project) -> Iterable[Issue]:
    """CanIf PDU names must be globally unique (docs/EN/CanIf.md:42)."""
    if not project.canif:
        return
    seen: dict[str, tuple[int, int, str]] = {}
    for ni, net in enumerate(project.canif.networks):
        for direction, pdus in (("RxPdus", net.RxPdus), ("TxPdus", net.TxPdus)):
            for pi, pdu in enumerate(pdus):
                if pdu.name in seen:
                    prev_ni, prev_pi, prev_dir = seen[pdu.name]
                    yield Issue(
                        rule="canif.pdu-names-unique",
                        severity=Severity.ERROR,
                        message=(
                            f"CanIf PDU name {pdu.name!r} appears more than once "
                            f"(first at networks[{prev_ni}].{prev_dir}[{prev_pi}], "
                            f"again at networks[{ni}].{direction}[{pi}])."
                        ),
                        location=Location("CanIf", ("networks", ni, direction, pi)),
                        fix=None,  # name collisions need a human decision
                    )
                else:
                    seen[pdu.name] = (ni, pi, direction)


@_rule
def cantp_requires_canif_pdus(project: Project) -> Iterable[Issue]:
    """CanTp channel X requires CanIf X_RX and X_TX with up: 'CanTp'.

    (docs/EN/CanTp.md:78-92; docs/AUTOAS_NOTES.md §1.3 rule 2.)
    """
    if not project.cantp or not project.canif:
        return
    rx_names = project.canif_rx_pdu_names()
    tx_names = project.canif_tx_pdu_names()
    canif_network_idx = 0  # default target for fix; rule R3 brings extra networks in

    for ci, channel in enumerate(project.cantp.channels):
        missing: list[tuple[str, str, set[str]]] = []
        if channel.name + "_RX" not in rx_names:
            missing.append(("RxPdus", channel.name + "_RX", rx_names))
        if channel.name + "_TX" not in tx_names:
            missing.append(("TxPdus", channel.name + "_TX", tx_names))
        if not missing:
            continue
        patches: list[dict[str, Any]] = []
        for direction, expected_name, _ in missing:
            patches.append(
                _patch_add(
                    f"/networks/{canif_network_idx}/{direction}/-",
                    {"name": expected_name, "id": "0x0", "hoh": 0, "up": "CanTp"},
                )
            )
        yield Issue(
            rule="cantp.requires-canif-pdus",
            severity=Severity.ERROR,
            message=(
                f"CanTp channel {channel.name!r} missing CanIf PDU(s): "
                + ", ".join(repr(name) for _, name, _ in missing)
            ),
            location=Location("CanTp", ("channels", ci)),
            fix=Fix(
                description=f"Add missing CanIf PDU(s) for CanTp channel {channel.name!r}",
                patches={"CanIf": patches},
            ),
        )


@_rule
def pdur_routine_endpoint_modules_configured(project: Project) -> Iterable[Issue]:
    """A PduR routine pointing at module X warns if X isn't in this project.

    The engine has no Dcm/SecOC/etc. models yet, so we only warn when the
    referenced module is one we DO model (CanIf, CanTp, Com) but the
    project doesn't include it.
    """
    if not project.pdur:
        return
    known = {
        "Can": project.can is not None,
        "CanIf": project.canif is not None,
        "CanTp": project.cantp is not None,
        "Com": project.com is not None,
    }
    for ri, routine in enumerate(project.pdur.routines):
        for endpoint_label, endpoint in (("from", routine.from_), ("to", routine.to)):
            if endpoint in known and not known[endpoint]:
                yield Issue(
                    rule="pdur.endpoint-module-configured",
                    severity=Severity.WARNING,
                    message=(
                        f"PduR routine {routine.name!r} {endpoint_label}={endpoint!r} "
                        f"but that module is not configured in this project."
                    ),
                    location=Location("PduR", ("routines", ri, endpoint_label)),
                    fix=None,
                )


@_rule
def canif_up_module_configured(project: Project) -> Iterable[Issue]:
    """CanIf 'up' module must be a known module or a User* callback name."""
    if not project.canif:
        return
    known = {
        "CanTp": project.cantp is not None,
        "PduR": project.pdur is not None,
        "Com": project.com is not None,
    }
    for ni, net in enumerate(project.canif.networks):
        for direction, pdus in (("RxPdus", net.RxPdus), ("TxPdus", net.TxPdus)):
            for pi, pdu in enumerate(pdus):
                # User callbacks are valid by upstream convention
                # (docs/EN/CanIf.md:78-100).
                if pdu.up.startswith("User"):
                    continue
                # Modules we don't model (OsekNm, CanNm, Xcp, …) — accept
                # them silently; out of engine's scope right now.
                if pdu.up not in known:
                    continue
                if not known[pdu.up]:
                    yield Issue(
                        rule="canif.up-module-configured",
                        severity=Severity.WARNING,
                        message=(
                            f"CanIf PDU {pdu.name!r} up={pdu.up!r} but that "
                            f"module is not configured in this project."
                        ),
                        location=Location(
                            "CanIf", ("networks", ni, direction, pi, "up")
                        ),
                        fix=None,
                    )


@_rule
def com_message_id_unique_per_network(project: Project) -> Iterable[Issue]:
    """Two messages on the same Com network can't share a CAN id."""
    if not project.com:
        return
    for ni, net in enumerate(project.com.networks):
        seen: dict[int, tuple[int, str]] = {}
        for mi, msg in enumerate(net.messages or []):
            try:
                msg_id = int(msg.id, 0)  # supports "0x.." and decimal
            except (TypeError, ValueError):
                # Out-of-format ids are caught by the schema; no rule clash.
                continue
            if msg_id in seen:
                prev_mi, prev_name = seen[msg_id]
                yield Issue(
                    rule="com.message-id-unique-per-network",
                    severity=Severity.ERROR,
                    message=(
                        f"Com network {net.name!r}: messages {prev_name!r} (idx {prev_mi}) "
                        f"and {msg.name!r} (idx {mi}) both use id {msg.id}."
                    ),
                    location=Location(
                        "Com", ("networks", ni, "messages", mi, "id")
                    ),
                    fix=None,
                )
            else:
                seen[msg_id] = (mi, msg.name)


@_rule
def com_message_has_canif_pdu(project: Project) -> Iterable[Issue]:
    """A Com message implies a same-named CanIf PDU exists in the right direction.

    Direction: Tx when message.node == network.me, else Rx
    (vendor/as Com.py convention; see derive.message_direction).

    Skipped when PduR or CanIf reference any module the engine doesn't
    model (SecOC, Mirror, Csm, …). Those configurations legitimately
    rename PDUs at every hop, so this simple rule would false-positive.
    """
    if not project.com or not project.canif:
        return
    if _has_unmodeled_intermediates(project):
        return
    rx_names = project.canif_rx_pdu_names()
    tx_names = project.canif_tx_pdu_names()
    for ni, net in enumerate(project.com.networks):
        canif_idx = _canif_network_index(project, net.name)
        if canif_idx is None:
            # Handled by com.network-has-canif-network; skip cascading error.
            continue
        for mi, msg in enumerate(net.messages or []):
            direction = message_direction(msg, net)
            target_names = tx_names if direction == "Tx" else rx_names
            expected_name = derived_pdu_name(msg, net)
            # Tolerate the bare message name too — old configs may carry it.
            if expected_name in target_names or msg.name in target_names:
                continue
            expected_pdu = derive_canif_pdu_for_com_message(msg, net)
            field = "TxPdus" if direction == "Tx" else "RxPdus"
            yield Issue(
                rule="com.message-has-canif-pdu",
                severity=Severity.ERROR,
                message=(
                    f"Com {direction} message {msg.name!r} on {net.name!r} has no "
                    f"matching CanIf {field} entry."
                ),
                location=Location("Com", ("networks", ni, "messages", mi)),
                fix=Fix(
                    description=f"Add CanIf {field} entry for Com message {msg.name!r}",
                    patches={
                        "CanIf": [
                            _patch_add(
                                f"/networks/{canif_idx}/{field}/-", expected_pdu
                            )
                        ]
                    },
                ),
            )


@_rule
def pdur_routine_has_canif_or_com_endpoint(project: Project) -> Iterable[Issue]:
    """A PduR routine that names a CanIf PDU should actually find one,
    and similarly when it names a Com message."""
    if not project.pdur:
        return
    canif_pdus = project.canif_pdu_names() if project.canif else set()
    com_msg_names = (
        {msg.name for _, msg in project.com_messages()}
        if project.com
        else set()
    )
    for ri, routine in enumerate(project.pdur.routines):
        # Only check when BOTH endpoints are modeled by the engine.
        # Routines through SecOC, Mirror, Dcm, etc. legitimately use names
        # that don't match Com message names or CanIf PDU names because
        # the wrapping module renames the PDU at each hop.
        if routine.from_ not in MODELED_MODULES or routine.to not in MODELED_MODULES:
            continue
        touches_canif = routine.from_ == "CanIf" or routine.to == "CanIf"
        touches_com = routine.from_ == "Com" or routine.to == "Com"
        if not touches_canif and not touches_com:
            continue
        # When CanIf is on either side, the routine name must match a CanIf PDU.
        if touches_canif and project.canif is not None:
            if routine.name not in canif_pdus:
                yield Issue(
                    rule="pdur.routine-name-resolves",
                    severity=Severity.ERROR,
                    message=(
                        f"PduR routine {routine.name!r} touches CanIf but no "
                        f"CanIf PDU with that name exists."
                    ),
                    location=Location("PduR", ("routines", ri, "name")),
                    fix=None,
                )
                continue
        # When Com is on either side but not CanIf, the name must match a Com message.
        if touches_com and not touches_canif and project.com is not None:
            if routine.name not in com_msg_names:
                yield Issue(
                    rule="pdur.routine-name-resolves",
                    severity=Severity.ERROR,
                    message=(
                        f"PduR routine {routine.name!r} touches Com but no Com "
                        f"message with that name exists."
                    ),
                    location=Location("PduR", ("routines", ri, "name")),
                    fix=None,
                )
