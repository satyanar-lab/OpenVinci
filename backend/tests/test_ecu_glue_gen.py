"""Integration-glue generator (backend/gen/ecu_glue.py, PROMPT C3).

Covers:
  - File set: EcuM.{c,h}, Sched.{c,h}, App.h, App_Demo.c
  - EcuM.c runs the BSW init chain in the right order
    (Can → CanIf → PduR → Com), then SetControllerMode + SetPduMode +
    Com_IpduGroupStart.
  - Sched.c defines SysTick_Handler and the handler pumps every
    Can/CanIf/Com MainFunction plus App_MainFunction.
  - App.h declares App_Init/App_MainFunction.
  - App_Demo.c uses Com_SendSignal / Com_ReceiveSignal with the
    project's signal names discovered automatically.
  - SysTick reload value matches the configured tick period at the
    documented 64 MHz HSI sysclk.
  - Host-only projects (no CanIf) emit nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

from engine import load_project
from gen import ecu_glue

REPO_ROOT = Path(__file__).resolve().parents[2]


# ----------------------------- file set -----------------------------


def test_h7_loopback_emits_full_glue_set(tmp_path: Path):
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    written = ecu_glue.generate(project, tmp_path)
    names = {p.name for p in written}
    assert names == {
        "EcuM.h",
        "EcuM.c",
        "Sched.h",
        "Sched.c",
        "App.h",
        "App_Demo.c",
    }


def test_skips_host_only_projects(tmp_path: Path):
    """No CanIf → host-only project → nothing to glue."""
    project = load_project(REPO_ROOT / "examples")  # not a project root
    assert ecu_glue.generate(project, tmp_path) == []


# ----------------------------- EcuM ---------------------------------


def test_ecum_runs_bsw_init_chain_in_order(tmp_path: Path):
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    ecu_glue.generate(project, tmp_path)
    body = (tmp_path / "EcuM.c").read_text()

    # The BSW chain must run in exactly Can → CanIf → PduR → Com
    # order — anything else and the BSW _MainFunction calls touch
    # uninitialised state.
    pos = [
        body.find("Can_Init("),
        body.find("CanIf_Init("),
        body.find("PduR_Init("),
        body.find("Com_Init("),
    ]
    assert all(p != -1 for p in pos), f"missing one of the Init calls in:\n{body}"
    assert pos == sorted(pos), f"init calls out of order at offsets {pos}"


def test_ecum_brings_controllers_up_and_starts_ipdu_groups(tmp_path: Path):
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    ecu_glue.generate(project, tmp_path)
    body = (tmp_path / "EcuM.c").read_text()
    assert "CanIf_SetControllerMode(0u, CAN_CS_STARTED)" in body
    assert "CanIf_SetPduMode(0u, CANIF_ONLINE)" in body
    assert "Com_IpduGroupStart(0u, TRUE)" in body


def test_ecum_owns_main_entrypoint_and_idles_in_wfi(tmp_path: Path):
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    ecu_glue.generate(project, tmp_path)
    body = (tmp_path / "EcuM.c").read_text()
    assert "int main(void)" in body
    assert "__WFI()" in body

    # And the init order in main: system clock → board → BSW → app →
    # scheduler. Use rfind so we anchor on the call sites — earlier
    # occurrences live in the docstring listing the same steps.
    main_start = body.rfind("int main(void)")
    assert main_start != -1
    main_body = body[main_start:]
    pos = [
        main_body.find("system_init_for_fdcan()"),
        main_body.find("board_init()"),
        main_body.find("EcuM_Init()"),
        main_body.find("App_Init()"),
        main_body.find("Sched_Init()"),
    ]
    assert all(p != -1 for p in pos), pos
    assert pos == sorted(pos), pos


# ----------------------------- Sched --------------------------------


def test_sched_defines_systick_handler_pumping_all_mainfunctions(tmp_path: Path):
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    ecu_glue.generate(project, tmp_path)
    body = (tmp_path / "Sched.c").read_text()

    assert "void SysTick_Handler(void)" in body
    for call in (
        "Can_MainFunction_Write()",
        "Can_MainFunction_Read()",
        "CanIf_MainFunction()",
        "Com_MainFunctionRx()",
        "Com_MainFunctionTx()",
        "App_MainFunction()",
    ):
        assert call in body, f"SysTick_Handler missing {call}:\n{body}"


def test_sched_reload_matches_tick_period_at_64mhz(tmp_path: Path):
    """Default tick is 1 ms; SysTick reload = HSI 64 MHz / 1000 = 64000."""
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    ecu_glue.generate(project, tmp_path)
    body = (tmp_path / "Sched.c").read_text()
    assert "SysTick_Config((uint32_t)64000u)" in body


def test_sched_reload_scales_with_tick_period(tmp_path: Path):
    """A 5 ms tick at 64 MHz → SysTick reload = 320000."""
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    ecu_glue.generate(project, tmp_path, tick_period_ms=5)
    body = (tmp_path / "Sched.c").read_text()
    assert "SysTick_Config((uint32_t)320000u)" in body
    # And Sched.h exposes the tick period for App_Demo's timing math.
    h_body = (tmp_path / "Sched.h").read_text()
    assert "OPENVINCI_TICK_PERIOD_MS 5u" in h_body


# ----------------------------- App seam -----------------------------


def test_app_h_declares_dev_seam(tmp_path: Path):
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    ecu_glue.generate(project, tmp_path)
    body = (tmp_path / "App.h").read_text()
    assert "void App_Init(void)" in body
    assert "void App_MainFunction(void)" in body


def test_app_demo_drives_loopback_via_com_signals(tmp_path: Path):
    """h7-loopback has TxSignal (sent) and RxSignal (received) — the
    demo should pick those up by name and route them through
    Com_SendSignal / Com_ReceiveSignal."""
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    ecu_glue.generate(project, tmp_path)
    body = (tmp_path / "App_Demo.c").read_text()

    assert "Com_SendSignal(COM_SID_TxSignal" in body
    assert "Com_ReceiveSignal(COM_SID_RxSignal" in body
    # The "RX=0xNN" print proves the loopback rt — same string the
    # H3-era manual main.c uses, so the same hardware test passes
    # against either variant.
    assert re.search(r'board_vcp_puts\("openvinci-h7: RX=0x"\)', body), body
    assert "board_vcp_put_hex8" in body
    # REPLACE ME banner so a real-app developer notices.
    assert "REPLACE ME" in body
