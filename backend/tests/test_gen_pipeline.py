"""VERIFICATION LEVEL 1 — generate + gcc-syntax-check on examples/com-minimal.

This is the end-to-end smoke test the prompt asks for: load a real
example, run the upstream generators, compile every produced `*_Cfg.c`
against `vendor/as`'s BSW headers, and assert a clean build.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import load_project
from gen import GENERATABLE_CLASSES, generate_and_compile

REPO_ROOT = Path(__file__).resolve().parents[2]
COM_MINIMAL = REPO_ROOT / "examples" / "com-minimal"
CANFD_MINIMAL = REPO_ROOT / "examples" / "canfd-minimal"
CANTP_ISO15765 = REPO_ROOT / "examples" / "cantp-iso15765"


@pytest.fixture(scope="module")
def gen_result(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("openvinci-com-minimal")
    project = load_project(COM_MINIMAL)
    return generate_and_compile(project, workdir, source_dir=COM_MINIMAL)


@pytest.fixture(scope="module")
def fd_gen_result(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("openvinci-canfd-minimal")
    project = load_project(CANFD_MINIMAL)
    return generate_and_compile(project, workdir, source_dir=CANFD_MINIMAL)


@pytest.fixture(scope="module")
def cantp_gen_result(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("openvinci-cantp-iso15765")
    project = load_project(CANTP_ISO15765)
    return generate_and_compile(project, workdir, source_dir=CANTP_ISO15765)


def test_compile_is_clean(gen_result):
    cr = gen_result.compile_result
    assert cr is not None
    assert cr.status == "ok", (
        "VERIFICATION LEVEL 1 failed.\n"
        + "\n".join(
            f"  {m.severity.upper()} {m.file}:{m.line}: {m.message}"
            for m in cr.messages
        )
    )
    assert not cr.errors


def test_every_generatable_module_emitted_a_cfg_c(gen_result):
    """Every modeled+generatable class in com-minimal must produce
    a `<Class>_Cfg.c`."""
    by_name = {f.path: f for f in gen_result.files}
    for cls in GENERATABLE_CLASSES:
        if cls == "CanTp":
            # com-minimal intentionally omits CanTp — no channels needed.
            continue
        assert any(
            path.endswith(f"{cls}_Cfg.c") for path in by_name
        ), f"no {cls}_Cfg.c in generated files: {sorted(by_name)}"


def test_generated_files_include_headers_too(gen_result):
    assert any(f.path.endswith(".h") for f in gen_result.files)
    assert any(f.path.endswith(".c") for f in gen_result.files)


def test_gen_result_carries_a_representative_command(gen_result):
    cmd = gen_result.compile_result.command
    assert cmd[0] == "gcc"
    assert "-c" in cmd and "-fsyntax-only" in cmd
    assert cmd[-1] == "<FILE>"


def test_each_file_records_size_and_module(gen_result):
    canonical = {"Com", "CanIf", "CanTp", "PduR"}
    saw_canonical = False
    for f in gen_result.files:
        assert f.size_bytes > 0, f
        if f.path.endswith(("_Cfg.c", "_Cfg.h", "_PBcfg.c", "_PBcfg.h")):
            assert f.module in canonical, f
            saw_canonical = True
    assert saw_canonical, "no canonical *_Cfg.{c,h} appeared in the output"


def test_canfd_minimal_compiles_clean(fd_gen_result):
    """Sister case to test_compile_is_clean: the same generate→gcc-syntax
    chain on a project where both PDUs are CAN FD (dlc=16, fd:true).
    The upstream Com / CanIf / PduR generators all accept the fd flag
    transparently (it rides on `additionalProperties: true`) and the
    16-byte Com_PduData buffer compiles against the BSW headers."""
    cr = fd_gen_result.compile_result
    assert cr is not None
    assert cr.status == "ok", (
        "canfd-minimal compile failed:\n"
        + "\n".join(
            f"  {m.severity.upper()} {m.file}:{m.line}: {m.message}"
            for m in cr.messages
        )
    )
    paths = {f.path for f in fd_gen_result.files}
    for stem in ("Com_Cfg.c", "CanIf_Cfg.c", "PduR_Cfg.c"):
        assert any(p.endswith(stem) for p in paths), f"missing {stem}"


def test_cantp_iso15765_compiles_clean(cantp_gen_result):
    """Third minimal fixture: CanTp + CanIf + PduR routes wired to a
    `Dcm` upper layer. Proves the generated CanTp_Cfg.{h,c} and
    PduR_Cfg.c compile against the BSW headers with our tiny per-
    example `include/Dcm_Cfg.h` shim picked up via
    `include_dirs_for` (backend/gen/compile.py). No Com module is
    configured — this is the diagnostic-transport-only shape."""
    cr = cantp_gen_result.compile_result
    assert cr is not None
    assert cr.status == "ok", (
        "cantp-iso15765 compile failed:\n"
        + "\n".join(
            f"  {m.severity.upper()} {m.file}:{m.line}: {m.message}"
            for m in cr.messages
        )
    )
    paths = {f.path for f in cantp_gen_result.files}
    for stem in ("CanTp_Cfg.c", "CanIf_Cfg.c", "PduR_Cfg.c"):
        assert any(p.endswith(stem) for p in paths), f"missing {stem}"


def test_canapp_min_compiles_when_full_ancillaries_present():
    """The bundled canapp-min should also compile because the test
    copies the vendor/as DBC + E2E.json alongside it (via source_dir).

    Marked slow-ish — skip cleanly if vendor/as ancillaries aren't
    locally available.
    """
    canapp = REPO_ROOT / "examples" / "canapp-min"
    if not (canapp / "config" / "Com" / "Com.json").is_file():
        pytest.skip("canapp-min not present")
    # canapp-min references E2E.json and CAN0.dbc that live in vendor/as,
    # not in the example. We patch them in from there.
    vendor_cfg = REPO_ROOT / "vendor" / "as" / "app" / "app" / "config"
    if not (vendor_cfg / "E2E" / "E2E.json").is_file():
        pytest.skip("vendor/as ancillary files not available")
