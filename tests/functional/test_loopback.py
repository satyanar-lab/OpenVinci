"""VERIFICATION LEVEL 2 — functional loopback through vendor/as's host simulator.

The harness builds the upstream CAN simulator broker directly via gcc
(no scons → no crypto/lua dependency cliffs) and exercises the full
TCP CAN bus protocol with three node-like clients:

  generate-and-compile (L1) confirms the generated files are valid C
  for the BSW. This test (L2) confirms the *runtime* simulation
  infrastructure transports frames end-to-end with the exact wire
  format the simulator-platform Can driver expects.

Set `OPENVINCI_RUN_FUNCTIONAL=1` to enable; otherwise the tests skip.

TestComStackLoopback closes the deep L2 gap: the node_binary fixture
links our generated `*_Cfg.c` with Com.c + CanIf.c + PduR.c + mcal
Can.c and the simulator Can driver (path (b) above). Init sequence and
MainFunction pumping mirror what `vendor/as/app/app/main.c` does for
the relevant layers. See `tests/functional/node/node_main.c`.

TestCanFdLoopback proves the same end-to-end claim at an FD-sized PDU
(dlc=16). The fd_node_binary fixture builds a sister node from
examples/canfd-minimal whose Com config emits a 16-byte UINT8N signal
on a CAN-FD-marked PDU; the Tx test asserts the broker sees the
configured 16 bytes byte-exact at id 0x200, the Rx test injects 16
bytes at id 0x201 and asserts Com_ReceiveSignal returns them all
byte-exact — proving the FD-sized data path through the OpenVinci-
emitted Com/CanIf/PduR config plus the upstream BSW.
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import pytest

from . import conftest as cf
from .conftest import (
    CAN_FRAME_SIZE,
    connect_node,
    decode_frame,
    encode_frame,
)


def _wait_for_node_ready(log_path: Path, *, timeout: float) -> None:
    """The node's main.c writes 'openvinci-node: ... up.' to stderr
    after pumping the stack long enough for the simulator Can driver
    to land its TCP socket on the broker. Block until we see it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log_path.is_file() and "up." in log_path.read_text():
            return
        time.sleep(0.05)
    raise RuntimeError(
        f"node did not report 'up.' within {timeout}s:\n"
        + (log_path.read_text() if log_path.is_file() else "(no log)")
    )


def _wait_for_log_contains(log_path: Path, needle: str, *, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log_path.is_file() and needle in log_path.read_text():
            return
        time.sleep(0.05)
    # Caller will assert and surface the log content.


# --- baseline: broker + raw socket clients ----------------------------


class TestBrokerLoopback:
    """The broker itself is part of the runtime stack. If it routes a
    frame from one node to another with byte-exact payload preservation
    and the right wire format, the simulator-platform Can driver will
    interoperate."""

    def test_broker_starts_and_listens(self, broker):
        # The fixture already asserts the broker accepted a TCP connection.
        assert broker.poll() is None  # still running

    def test_frame_round_trip_preserves_id_and_payload(
        self, broker, free_can_port: int
    ):
        sender = connect_node(free_can_port)
        receiver = connect_node(free_can_port)
        # Give the broker a moment to register both peers.
        time.sleep(0.2)
        payload = b"\xde\xad\xbe\xef\x01\x02\x03\x04"
        sender.send(encode_frame(0x100, payload))
        receiver.settimeout(2.0)
        canid, got = decode_frame(receiver.recv(CAN_FRAME_SIZE))
        assert canid == 0x100
        assert got == payload
        sender.close()
        receiver.close()

    def test_sender_does_not_receive_own_frame(self, broker, free_can_port: int):
        """vendor/as's broker filters echoes back to the sender."""
        sender = connect_node(free_can_port)
        receiver = connect_node(free_can_port)
        time.sleep(0.2)
        sender.send(encode_frame(0x200, b"\xaa\xbb"))
        # Drain receiver so the broker keeps flowing
        receiver.settimeout(1.0)
        _ = receiver.recv(CAN_FRAME_SIZE)
        sender.settimeout(0.5)
        with pytest.raises((socket.timeout, TimeoutError)):
            sender.recv(CAN_FRAME_SIZE)
        sender.close()
        receiver.close()

    def test_multi_id_routing(self, broker, free_can_port: int):
        """Three message IDs in flight at once; all arrive correctly."""
        sender = connect_node(free_can_port)
        receiver = connect_node(free_can_port)
        time.sleep(0.2)
        ids = [0x100, 0x101, 0x102]
        for can_id in ids:
            sender.send(encode_frame(can_id, bytes([can_id & 0xFF] * 4)))
        receiver.settimeout(2.0)
        seen = set()
        for _ in ids:
            canid, payload = decode_frame(receiver.recv(CAN_FRAME_SIZE))
            seen.add(canid)
        assert seen == set(ids)
        sender.close()
        receiver.close()


# --- end-to-end with a COM-stack-linked node --------------------------


class TestComStackLoopback:
    """End-to-end through the real COM stack with our generated config.

    The node_binary fixture (conftest.py) stages examples/com-minimal,
    runs the upstream generators against it, then gcc-links the
    resulting *_Cfg.c with Com / CanIf / PduR / mcal-Can and the
    simulator Can driver. The two tests below drive its two CLI modes."""

    def test_node_transmits_periodic_tx_message(
        self, broker, node_binary: Path, free_can_port: int
    ):
        log_path = cf.BUILD_DIR / f"node-{free_can_port}.log"
        log = log_path.open("w")
        node = subprocess.Popen(
            [str(node_binary), "--bus", str(free_can_port)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_node_ready(log_path, timeout=5.0)
            listener = connect_node(free_can_port)
            listener.settimeout(3.0)
            # com-minimal's TX_MSG has CycleTime=1000 and id=0x100; the
            # node should send within ~1s of starting.
            canid, _ = decode_frame(listener.recv(CAN_FRAME_SIZE))
            assert canid == 0x100, f"expected the configured Tx id, got 0x{canid:x}"
            listener.close()
        finally:
            node.terminate()
            try:
                node.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                node.kill()
            log.close()

    def test_node_receives_injected_frame_and_logs_signal(
        self, broker, node_binary: Path, free_can_port: int
    ):
        log_path = cf.BUILD_DIR / f"node-rx-{free_can_port}.log"
        log = log_path.open("w")
        node = subprocess.Popen(
            [str(node_binary), "--bus", str(free_can_port), "--probe"],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_node_ready(log_path, timeout=5.0)
            tester = connect_node(free_can_port)
            # Broker registers new sockets via select(); give it a
            # round-trip to land the tester before injecting.
            time.sleep(0.4)
            # com-minimal's RX_MSG id is 0x101; payload[0] should land
            # in the RxSignal slot.
            tester.send(encode_frame(0x101, b"\x42" + b"\x00" * 7))
            # Keep the tester connection open while polling so the broker
            # doesn't tear it down before the frame is forwarded.
            _wait_for_log_contains(log_path, "RxSignal=0x42", timeout=3.0)
            tester.close()
        finally:
            node.terminate()
            try:
                node.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                node.kill()
            log.close()
        log_text = log_path.read_text()
        assert "RxSignal=0x42" in log_text, (
            "node did not log the expected Rx signal value:\n" + log_text
        )


# --- end-to-end with a CAN-FD COM-stack-linked node -------------------


class TestCanFdLoopback:
    """End-to-end through the real COM stack with our generated CAN-FD
    config (examples/canfd-minimal).

    Same shape as TestComStackLoopback but with an FD-sized PDU
    (dlc=16) and a 16-byte UINT8N signal on each direction. The
    fd_node_binary fixture stages canfd-minimal, runs the upstream
    generators against it, gcc-links the resulting *_Cfg.c with the
    same Com / CanIf / PduR / mcal-Can sources + simulator Can driver,
    and produces a binary that drives the FD PDUs through their two
    CLI modes."""

    # The 16-byte payload node_fd_main.c writes via Com_SendSignal on
    # TxFdSignal. Kept in sync with k_tx_payload in
    # tests/functional/node/node_fd_main.c — the test treats it as
    # ground truth and the assertion is on the broker's view of the
    # wire frame.
    _TX_PAYLOAD: bytes = bytes(
        [
            0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
            0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51,
        ]
    )

    # Distinct injected payload for the Rx direction — every byte
    # different from _TX_PAYLOAD and from the Com zero-init buffer, so
    # any mistaken echo or stub would be obvious.
    _RX_PAYLOAD: bytes = bytes(
        [
            0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11,
            0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99,
        ]
    )

    def test_node_transmits_fd_frame_at_configured_dlc(
        self, broker, fd_node_binary: Path, free_can_port: int
    ):
        log_path = cf.BUILD_DIR / f"fd-node-{free_can_port}.log"
        log = log_path.open("w")
        node = subprocess.Popen(
            [str(fd_node_binary), "--bus", str(free_can_port)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_node_ready(log_path, timeout=5.0)
            listener = connect_node(free_can_port)
            # CycleTime=1000 on canfd-minimal's TX_FD_MSG; one frame
            # within ~1 s after the node starts.
            listener.settimeout(3.0)
            canid, payload = decode_frame(listener.recv(CAN_FRAME_SIZE))
            assert canid == 0x200, f"expected configured FD Tx id, got 0x{canid:x}"
            # The dlc field of the broker's wire frame must reflect the
            # 16-byte FD PDU we generated. The 0..7 case would happily
            # pass a "this is Classic CAN" check, so testing this is the
            # core of the L2 FD claim.
            assert len(payload) == 16, (
                f"FD wire dlc must be 16; got {len(payload)} byte frame: "
                f"{payload.hex()}"
            )
            # Bytes must be the exact constant the node Com_SendSignal'd
            # — nothing about the simulator path is allowed to drop or
            # rewrite them.
            assert payload == self._TX_PAYLOAD, (
                f"FD Tx payload mismatch:\n  expected: {self._TX_PAYLOAD.hex()}\n"
                f"  got:      {payload.hex()}"
            )
            listener.close()
        finally:
            node.terminate()
            try:
                node.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                node.kill()
            log.close()

    def test_node_receives_fd_frame_and_logs_full_payload(
        self, broker, fd_node_binary: Path, free_can_port: int
    ):
        log_path = cf.BUILD_DIR / f"fd-node-rx-{free_can_port}.log"
        log = log_path.open("w")
        node = subprocess.Popen(
            [str(fd_node_binary), "--bus", str(free_can_port), "--probe"],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_node_ready(log_path, timeout=5.0)
            tester = connect_node(free_can_port)
            # Broker registers new sockets via select(); give it a
            # round-trip to land the tester before injecting.
            time.sleep(0.4)
            # canfd-minimal's RX_FD_MSG id is 0x201, dlc=16; the
            # injected 16 bytes should land in the RxFdSignal slot
            # byte-exact.
            tester.send(encode_frame(0x201, self._RX_PAYLOAD))
            expected_line = f"RxFdSignal={self._RX_PAYLOAD.hex()}"
            _wait_for_log_contains(log_path, expected_line, timeout=3.0)
            tester.close()
        finally:
            node.terminate()
            try:
                node.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                node.kill()
            log.close()
        log_text = log_path.read_text()
        expected_line = f"RxFdSignal={self._RX_PAYLOAD.hex()}"
        assert expected_line in log_text, (
            "node did not log the expected Rx FD payload (must come from "
            "Com_ReceiveSignal — nothing is hardcoded in node_fd_main.c):\n"
            + log_text
        )
