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
