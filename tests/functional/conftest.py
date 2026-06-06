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
NODE_BIN = BUILD_DIR / "openvinci_node"
NODE_GEN_DIR = BUILD_DIR / "com-minimal"
NODE_SRC_DIR = Path(__file__).parent / "node"


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


# --- node (real COM-stack-linked) -------------------------------------

# Upstream BSW sources we link. The Com / CanIf / PduR / mcal-Can files
# are the production stack; the simulator Can driver + canlib + the
# TCP simulator backend give us the wire layer that talks to the
# broker; std_timer + std_bit + mempool + critical + Log/PAL are the
# infrastructure those modules pull in. We intentionally don't link
# Dcm / NM / Xcp / SecOC — com-minimal doesn't reference them and
# they'd pull crypto / lua we can't fetch.
_NODE_C_SRC_REL: tuple[str, ...] = (
    "infras/communication/Com/Com.c",
    "infras/communication/CanIf/CanIf.c",
    "infras/communication/PduR/PduR.c",
    "infras/communication/PduR/PduR_Com.c",
    "infras/communication/PduR/PduR_CanIf.c",
    "infras/mcal/Can/Can.c",
    "infras/libraries/stdbit/src/std_bit.c",
    "infras/libraries/mempool/mempool.c",
    "infras/system/timer/std_timer.c",
    "infras/communication/TcpIp/TcpIp.c",
    "infras/communication/TcpIp/config/TcpIp_Cfg.c",
    "app/platform/simulator/src/config/Can_Cfg.c",
)
_NODE_CPP_SRC_REL: tuple[str, ...] = (
    "app/platform/simulator/src/Can.cpp",
    "app/platform/simulator/src/critical.cpp",
    "tools/libraries/Can/src/canlib.cpp",
    "tools/libraries/Can/src/simulator_can.cpp",
    "tools/libraries/Can/src/simulator_can_v2.cpp",
    "tools/libraries/Can/src/qemu_serial_vcan.cpp",
    "tools/libraries/utils/src/Log.cpp",
    "tools/libraries/utils/src/PAL.cpp",
)
_NODE_INCLUDE_REL: tuple[str, ...] = (
    "infras/include",
    "infras/mcal/Can",
    "infras/communication/Com",
    "infras/communication/CanIf",
    "infras/communication/PduR",
    "infras/communication/E2E",
    "infras/communication/TcpIp",
    "infras/libraries/stdbit/src",
    "infras/libraries/mempool",
    "tools/libraries/Can/include",
    "tools/libraries/Can/src",
    "tools/libraries/utils/include",
    "app/platform/simulator/src/config",
)


@pytest.fixture(scope="session")
def node_binary(opt_in, broker_binary) -> Path:  # noqa: ARG001 (opt_in is a gate)
    """Build the minimal COM-stack node from examples/com-minimal.

    Stages the example, runs the upstream generators in-process, then
    gcc-links the result with Com.c / CanIf.c / PduR.c / mcal-Can.c
    and the simulator Can driver + canlib. The binary supports the
    two CLI modes the tests already exercise (`--bus N`, `--probe`).
    """
    if NODE_BIN.is_file() and _node_inputs_unchanged():
        return NODE_BIN

    NODE_GEN_DIR.mkdir(parents=True, exist_ok=True)
    _stage_and_generate_com_minimal()
    gen_dir = NODE_GEN_DIR / "config" / "Com" / "GEN"

    sources_c = [VENDOR_AS / rel for rel in _NODE_C_SRC_REL] + [
        gen_dir / "Com_Cfg.c",
        gen_dir / "CanIf_Cfg.c",
        gen_dir / "PduR_Cfg.c",
        NODE_SRC_DIR / "node_main.c",
        NODE_SRC_DIR / "node_glue.c",
    ]
    sources_cpp = [VENDOR_AS / rel for rel in _NODE_CPP_SRC_REL]
    for src in sources_c + sources_cpp:
        if not src.is_file():
            pytest.skip(f"missing source: {src}")

    cmd: list[str] = [
        "g++",
        "-O0",
        "-g",
        "-DPATH_MAX=4096",
        "-DUSE_STD_PRINTF",
        "-DUSE_CAN",
        "-DUSE_CANIF",
        "-DUSE_COM",
        "-DUSE_PDUR",
    ]
    for rel in _NODE_INCLUDE_REL:
        cmd.append(f"-I{VENDOR_AS / rel}")
    cmd.append(f"-I{gen_dir}")
    for src in sources_c:
        cmd += ["-x", "c", str(src)]
    for src in sources_cpp:
        cmd += ["-x", "c++", str(src)]
    cmd += ["-lpthread", "-luuid", "-o", str(NODE_BIN)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log = BUILD_DIR / "node-build.log"
        log.write_text(proc.stdout + proc.stderr)
        pytest.skip(
            f"node build failed (see {log.relative_to(REPO_ROOT)}):\n"
            + proc.stderr[-2000:]
        )
    return NODE_BIN


def _stage_and_generate_com_minimal() -> None:
    """Copy examples/com-minimal into the build dir and run the upstream
    generators against it — same path the L1 gen pipeline uses, just
    rooted at build/functional/com-minimal so we can re-link without
    touching the example tree."""
    src = REPO_ROOT / "examples" / "com-minimal"
    dst = NODE_GEN_DIR
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    cfgs = [
        str(dst / "config" / "Com" / "Com.json"),
        str(dst / "config" / "Com" / "CanIf.json"),
        str(dst / "config" / "Com" / "PduR.json"),
    ]
    tools = str(VENDOR_AS / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import generator  # type: ignore[import-not-found]

    saved_root = generator.RootDir
    generator.RootDir = str(dst)
    try:
        generator.Generate(cfgs, force=True)
    finally:
        generator.RootDir = saved_root


def _node_inputs_unchanged() -> bool:
    """Tiny cache: skip the rebuild if node_main.c + node_glue.c haven't
    changed since the binary was produced. Saves ~5 s on repeat runs."""
    inputs = [
        NODE_SRC_DIR / "node_main.c",
        NODE_SRC_DIR / "node_glue.c",
    ]
    if not all(p.is_file() for p in inputs):
        return False
    bin_mtime = NODE_BIN.stat().st_mtime
    return all(p.stat().st_mtime <= bin_mtime for p in inputs)


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
