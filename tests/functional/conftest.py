"""Functional-test fixtures: build the broker, build a node, manage processes.

The harness lives outside backend/tests/ because (a) it needs `gcc` and
`vendor/as` sources, not just Python, and (b) it's slow — running the full
unit suite on every change shouldn't drag in process spawning.

Two artifacts get built:

1. **broker** (`can_simulator`) — vendor/as's TCP CAN broker. Compiled
   directly with gcc from a small set of vendor/as sources (TcpIp,
   std_timer, utils, the broker itself). Proven buildable in this
   environment.

2. **node** — a minimal COM-stack node that links our generated
   `*_Cfg.c` files with the BSW sources from `vendor/as/infras/`.
   Best-effort: if the build fails (e.g. missing Os/Mcu deps that
   upstream's CanApp pulls in), the test that needs it skips with a
   clear message rather than failing.

Set `OPENVINCI_RUN_FUNCTIONAL=1` to opt in to the slow tests.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_AS = REPO_ROOT / "vendor" / "as"
BUILD_DIR = REPO_ROOT / "build" / "functional"
BROKER_BIN = BUILD_DIR / "can_simulator"


def _functional_enabled() -> bool:
    return os.environ.get("OPENVINCI_RUN_FUNCTIONAL") == "1"


@pytest.fixture(scope="session")
def opt_in() -> None:
    if not _functional_enabled():
        pytest.skip(
            "set OPENVINCI_RUN_FUNCTIONAL=1 to run the slow functional suite",
            allow_module_level=False,
        )


@pytest.fixture(scope="session")
def broker_binary(opt_in) -> Path:  # noqa: ARG001 (opt_in is a gate)
    """Build vendor/as's can_simulator broker directly via gcc.

    Vendor/as ships an SConscript that uses `--lib=AsOne` / lua / mbedtls,
    which need network-accessible mirrors we don't have. The broker
    itself is just `can_simulator.c` + TcpIp + std_timer + a small
    utils chunk — compiles cleanly with a few -I flags.
    """
    if BROKER_BIN.is_file():
        return BROKER_BIN
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    sources = [
        VENDOR_AS / "tools/libraries/Can/utils/can_simulator.c",
        VENDOR_AS / "infras/communication/TcpIp/TcpIp.c",
        VENDOR_AS / "infras/communication/TcpIp/config/TcpIp_Cfg.c",
        VENDOR_AS / "infras/system/timer/std_timer.c",
        VENDOR_AS / "tools/libraries/utils/src/Log.cpp",
        VENDOR_AS / "tools/libraries/utils/src/PAL.cpp",
    ]
    for src in sources:
        if not src.is_file():
            pytest.skip(f"missing vendor/as source: {src.relative_to(REPO_ROOT)}")
    cmd: list[str] = [
        "g++",
        "-O0",
        "-g",
        "-DPATH_MAX=4096",
        "-DUSE_STD_PRINTF",
        f"-I{VENDOR_AS}/infras/include",
        f"-I{VENDOR_AS}/infras/communication/TcpIp",
        f"-I{VENDOR_AS}/tools/libraries/utils/include",
    ]
    # g++'s -x flag only applies to the next file (per the man page); repeat
    # explicitly so .c sources are not treated as C++ (where extern-C linkage
    # bites us via name mangling on `TcpIp_Config` etc.).
    for src in sources:
        cmd += ["-x", "c++" if src.suffix == ".cpp" else "c", str(src)]
    cmd += ["-lpthread", "-o", str(BROKER_BIN)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip(
            "broker build failed:\n"
            + proc.stdout
            + proc.stderr
        )
    return BROKER_BIN


@pytest.fixture
def broker(broker_binary: Path, free_can_port: int) -> Iterator[subprocess.Popen]:
    """Start the broker on a free CAN bus port for the duration of the test."""
    log = (BUILD_DIR / f"broker-{free_can_port}.log").open("w")
    proc = subprocess.Popen(
        [str(broker_binary), str(free_can_port)],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_tcp("127.0.0.1", 8000 + free_can_port, timeout=3.0)
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


@pytest.fixture
def free_can_port() -> int:
    """Pick a CAN bus index whose corresponding TCP port (8000+i) is free.

    Bus 0 maps to port 8000 which collides with the FastAPI dev server,
    so the test always uses ≥10."""
    for candidate in range(10, 30):
        tcp_port = 8000 + candidate
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", tcp_port))
            except OSError:
                continue
            return candidate
    pytest.skip("could not find a free CAN bus port in [10, 30)")


def _wait_for_tcp(host: str, port: int, *, timeout: float) -> None:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.1)
    raise RuntimeError(f"{host}:{port} did not come up in {timeout}s: {last_err}")


# --- shared protocol helpers ------------------------------------------

CAN_MAX_DLEN = 64
CAN_FRAME_SIZE = CAN_MAX_DLEN + 5


def encode_frame(canid: int, data: bytes) -> bytes:
    """vendor/as broker on-wire layout (see
    `tools/libraries/Can/src/simulator_can.cpp` mCANID/mSetCANID/mSetCANDLC).
    """
    buf = bytearray(CAN_FRAME_SIZE)
    dlc = len(data)
    buf[:dlc] = data
    buf[CAN_MAX_DLEN] = (canid >> 24) & 0xFF
    buf[CAN_MAX_DLEN + 1] = (canid >> 16) & 0xFF
    buf[CAN_MAX_DLEN + 2] = (canid >> 8) & 0xFF
    buf[CAN_MAX_DLEN + 3] = canid & 0xFF
    buf[CAN_MAX_DLEN + 4] = dlc
    return bytes(buf)


def decode_frame(buf: bytes) -> tuple[int, bytes]:
    canid = (
        (buf[CAN_MAX_DLEN] << 24)
        | (buf[CAN_MAX_DLEN + 1] << 16)
        | (buf[CAN_MAX_DLEN + 2] << 8)
        | buf[CAN_MAX_DLEN + 3]
    )
    dlc = buf[CAN_MAX_DLEN + 4]
    return canid, bytes(buf[:dlc])


def connect_node(bus: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", 8000 + bus))
    return s
