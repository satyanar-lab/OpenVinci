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
FD_NODE_BIN = BUILD_DIR / "openvinci_fd_node"
FD_NODE_GEN_DIR = BUILD_DIR / "canfd-minimal"
TP_NODE_BIN = BUILD_DIR / "openvinci_tp_node"
TP_NODE_GEN_DIR = BUILD_DIR / "cantp-iso15765"
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

# Shared upstream BSW sources every functional node links. The
# simulator Can driver + canlib + the TCP simulator backend give us
# the wire layer that talks to the broker; std_timer + std_bit +
# mempool + critical + Log/PAL are the infrastructure those modules
# pull in. We intentionally don't link Dcm / NM / Xcp / SecOC —
# they'd pull crypto / lua we can't fetch.
_NODE_BASE_C_SRC_REL: tuple[str, ...] = (
    "infras/communication/CanIf/CanIf.c",
    "infras/communication/PduR/PduR.c",
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
    "infras/communication/CanTp",
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

# Per-stack add-on C sources (each row says "if you USE_X, also link
# these"). Kept here so adding the next module is one line.
_NODE_COM_C_SRC_REL: tuple[str, ...] = (
    "infras/communication/Com/Com.c",
    "infras/communication/PduR/PduR_Com.c",
)
_NODE_CANTP_C_SRC_REL: tuple[str, ...] = (
    "infras/communication/CanTp/CanTp.c",
    "infras/communication/PduR/PduR_CanTp.c",
)


@pytest.fixture(scope="session")
def node_binary(opt_in, broker_binary) -> Path:  # noqa: ARG001 (opt_in is a gate)
    """Build the minimal COM-stack node from examples/com-minimal.

    Stages the example, runs the upstream generators in-process, then
    gcc-links the result with Com.c / CanIf.c / PduR.c / mcal-Can.c
    and the simulator Can driver + canlib. The binary supports the
    two CLI modes the tests already exercise (`--bus N`, `--probe`).
    """
    return _build_node_binary(
        example_name="com-minimal",
        gen_dir_root=NODE_GEN_DIR,
        node_main_filename="node_main.c",
        bin_path=NODE_BIN,
        build_log_name="node-build.log",
        use_com=True,
    )


@pytest.fixture(scope="session")
def fd_node_binary(opt_in, broker_binary) -> Path:  # noqa: ARG001 (opt_in is a gate)
    """Build the CAN-FD COM-stack node from examples/canfd-minimal.

    Sister of `node_binary`. Different generated `*_Cfg.c` (the FD
    config emits 16-byte Com_PduData buffers and a different signal id
    enum), different node main (node_fd_main.c uses the
    COM_SID_TxFdSignal / RxFdSignal symbols and a 16-byte UINT8N signal
    payload). Same vendor/as BSW sources and simulator driver.
    """
    return _build_node_binary(
        example_name="canfd-minimal",
        gen_dir_root=FD_NODE_GEN_DIR,
        node_main_filename="node_fd_main.c",
        bin_path=FD_NODE_BIN,
        build_log_name="fd-node-build.log",
        use_com=True,
    )


@pytest.fixture(scope="session")
def tp_node_binary(opt_in, broker_binary) -> Path:  # noqa: ARG001 (opt_in is a gate)
    """Build the CanTp (ISO-15765) node from examples/cantp-iso15765.

    No Com module — diagnostic transport only. node_tp_main.c
    initializes (Can, CanIf, PduR, CanTp), brings up the controller,
    and pumps the main functions in the order
    `vendor/as/app/bootloader/main.c:111-120` uses. The
    `node_tp_sink.c` provides the Dcm upper-layer API symbols the
    upstream PduR generator binds against (StartOfReception,
    CopyRxData, TpRxIndication, CopyTxData, TpTxConfirmation) — it
    does NOT implement segmentation; all SF/FF/FC/CF logic lives in
    the upstream CanTp.c we link.
    """
    return _build_node_binary(
        example_name="cantp-iso15765",
        gen_dir_root=TP_NODE_GEN_DIR,
        node_main_filename="node_tp_main.c",
        bin_path=TP_NODE_BIN,
        build_log_name="tp-node-build.log",
        use_com=False,
        use_cantp=True,
        extra_local_sources=("node_tp_sink.c",),
    )


def _build_node_binary(
    *,
    example_name: str,
    gen_dir_root: Path,
    node_main_filename: str,
    bin_path: Path,
    build_log_name: str,
    use_com: bool = True,
    use_cantp: bool = False,
    extra_local_sources: tuple[str, ...] = (),
) -> Path:
    """Stage an example, run the generators, gcc-link the resulting
    `*_Cfg.c` with the chosen node main + the shared BSW sources.

    Per-stack tweaks:
    - `use_com`   adds Com.c + PduR_Com.c and `-DUSE_COM`.
    - `use_cantp` adds CanTp.c + PduR_CanTp.c and `-DUSE_CANTP`.
    - `extra_local_sources` lists additional `tests/functional/node/`
      `.c` files to link (e.g. the Dcm sink for the TP node).

    Returns the binary path; skips the calling test cleanly (with the
    build log captured) if any step fails.
    """
    node_main_src = NODE_SRC_DIR / node_main_filename
    node_glue_src = NODE_SRC_DIR / "node_glue.c"
    extra_local_paths = [NODE_SRC_DIR / name for name in extra_local_sources]
    cached_inputs = [node_main_src, node_glue_src] + extra_local_paths
    if bin_path.is_file() and _node_inputs_unchanged(bin_path, cached_inputs):
        return bin_path

    gen_dir_root.mkdir(parents=True, exist_ok=True)
    _stage_and_generate(example_name, gen_dir_root)

    base_c = list(_NODE_BASE_C_SRC_REL)
    if use_com:
        base_c.extend(_NODE_COM_C_SRC_REL)
    if use_cantp:
        base_c.extend(_NODE_CANTP_C_SRC_REL)

    # Pick up every generated `*_Cfg.c` the upstream generator wrote
    # — the gen dirs differ per module (Com/GEN vs CanTp/GEN).
    gen_cfg_sources = sorted(gen_dir_root.rglob("*_Cfg.c"))
    if not gen_cfg_sources:
        pytest.skip(
            f"{example_name}: generator produced no *_Cfg.c under {gen_dir_root}"
        )

    sources_c = (
        [VENDOR_AS / rel for rel in base_c]
        + gen_cfg_sources
        + [node_main_src, node_glue_src]
        + extra_local_paths
    )
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
        "-DUSE_PDUR",
    ]
    if use_com:
        cmd.append("-DUSE_COM")
    if use_cantp:
        cmd.append("-DUSE_CANTP")
    for rel in _NODE_INCLUDE_REL:
        cmd.append(f"-I{VENDOR_AS / rel}")
    # All generator output dirs plus any per-example `include/` shim
    # (e.g. cantp-iso15765 ships a tiny Dcm_Cfg.h there).
    for d in sorted(gen_dir_root.rglob("GEN")):
        cmd.append(f"-I{d}")
    for d in sorted(gen_dir_root.rglob("include")):
        cmd.append(f"-I{d}")
    for src in sources_c:
        cmd += ["-x", "c", str(src)]
    for src in sources_cpp:
        cmd += ["-x", "c++", str(src)]
    cmd += ["-lpthread", "-luuid", "-o", str(bin_path)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log = BUILD_DIR / build_log_name
        log.write_text(proc.stdout + proc.stderr)
        pytest.skip(
            f"{example_name} node build failed (see "
            f"{log.relative_to(REPO_ROOT)}):\n"
            + proc.stderr[-2000:]
        )
    return bin_path


def _stage_and_generate(example_name: str, dst: Path) -> None:
    """Copy examples/<example_name> into `dst` and run the upstream
    generators against it — same path the L1 gen pipeline uses, just
    rooted at build/functional/<example_name> so we can re-link
    without touching the example tree."""
    src = REPO_ROOT / "examples" / example_name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    # Every recognised module JSON the upstream generator can consume.
    # cantp-iso15765 has no Com.json, com-minimal has no CanTp.json —
    # we just pass whichever ones exist.
    candidate_cfgs = [
        dst / "config" / "Com" / "Com.json",
        dst / "config" / "Com" / "CanIf.json",
        dst / "config" / "Com" / "PduR.json",
        dst / "config" / "CanTp" / "CanTp.json",
    ]
    cfgs = [str(p) for p in candidate_cfgs if p.is_file()]
    if not cfgs:
        raise RuntimeError(
            f"no recognised module JSONs under {dst}; expected at least one of "
            f"{[p.name for p in candidate_cfgs]}"
        )
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


def _node_inputs_unchanged(bin_path: Path, inputs: list[Path]) -> bool:
    """Tiny cache: skip the rebuild if the node main + glue haven't
    changed since the binary was produced. Saves ~5 s on repeat runs."""
    if not all(p.is_file() for p in inputs):
        return False
    bin_mtime = bin_path.stat().st_mtime
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


# --- ISO-15765 frame helpers ------------------------------------------
#
# Minimal encoders for the classic-CAN (LL_DL=8) PCI byte layout.
# Used by TestCanTpLoopback to act as the ISO-TP peer (the
# segmentation / reassembly itself lives in upstream CanTp.c).
#
# Frame layout (per ISO 15765-2):
#   SF: PCI=0x0L (L=length), data[0..L-1]
#   FF: PCI hi nibble=1, low nibble + next byte = 12-bit total length
#   CF: PCI hi nibble=2, low nibble = sequence number (1..15, wraps to 0)
#   FC: PCI hi nibble=3, low nibble = FS (0=CTS), then BS, then STmin


def isotp_single_frame(data: bytes, *, padding: int = 0xCC) -> bytes:
    if len(data) > 7:
        raise ValueError("SF payload must be <= 7 bytes on classic CAN")
    out = bytearray([len(data) & 0x0F])
    out.extend(data)
    while len(out) < 8:
        out.append(padding)
    return bytes(out)


def isotp_first_frame(total_length: int, data6: bytes, *, padding: int = 0xCC) -> bytes:
    if total_length > 0xFFF:
        raise ValueError("FF length must fit in 12 bits (escape not supported here)")
    if len(data6) != 6:
        raise ValueError("classic-CAN FF carries exactly 6 payload bytes")
    out = bytearray(
        [
            0x10 | ((total_length >> 8) & 0x0F),
            total_length & 0xFF,
        ]
    )
    out.extend(data6)
    while len(out) < 8:
        out.append(padding)
    return bytes(out)


def isotp_consecutive_frame(
    sequence_number: int, payload: bytes, *, padding: int = 0xCC
) -> bytes:
    if not 0 <= sequence_number <= 15:
        raise ValueError("CF SN is 4 bits (0..15)")
    if len(payload) > 7:
        raise ValueError("CF payload <= 7 bytes on classic CAN")
    out = bytearray([0x20 | (sequence_number & 0x0F)])
    out.extend(payload)
    while len(out) < 8:
        out.append(padding)
    return bytes(out)


def isotp_flow_control(
    flow_status: int = 0, *, block_size: int = 0, st_min: int = 0, padding: int = 0xCC
) -> bytes:
    """Flow Control. flow_status: 0=CTS, 1=Wait, 2=Overflow."""
    out = bytearray([0x30 | (flow_status & 0x0F), block_size & 0xFF, st_min & 0xFF])
    while len(out) < 8:
        out.append(padding)
    return bytes(out)


def isotp_parse_pci(payload: bytes) -> tuple[str, int]:
    """Return ("SF"|"FF"|"CF"|"FC"|"?", low-nibble value)."""
    if not payload:
        return "?", 0
    pci_hi = payload[0] >> 4
    pci_lo = payload[0] & 0x0F
    return {0: "SF", 1: "FF", 2: "CF", 3: "FC"}.get(pci_hi, "?"), pci_lo
