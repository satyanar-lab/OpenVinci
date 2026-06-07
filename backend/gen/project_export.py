"""STM32H753ZI project export (PROMPT C4).

Assembles a COMPLETE, self-contained, buildable STM32H7 firmware
project from an OpenVinci project tree. Combines four sources:

  1. FIXED template assets — Can_H7.c, system_init.c, board.c/h,
     linker script, Makefile.export. Copied verbatim from
     hardware/stm32h753zi/.

  2. autoas BSW sources — Com / PduR / CanIf / mcal-Can plus the
     std_bit + mempool libraries the BSW pulls in. Copied from
     vendor/as/infras/ so the export doesn't need the upstream
     submodule.

  3. Generated *_Cfg.{c,h} — vendor generator output (Com_Cfg /
     PduR_Cfg / CanIf_Cfg) plus our can_h7 backend (Can_Cfg). Same
     code path /api/generate uses.

  4. Generated glue — EcuM / Sched / App seam (ecu_glue) + the
     App_Demo "REPLACE ME" stub.

Plus a self-generated README.md walking the user through `make` and
`make flash`.

CMSIS dependencies (cmsis-device-h7 + CMSIS_5/Core) are bundled into
third_party/ so the exported project has NO references back to the
host OpenVinci repo. The exported folder is enough to build the
firmware with arm-none-eabi-gcc alone.

Entry points:
    assemble_h7_project(project, output_dir, source_dir=None)
    write_zip(project, source_dir=None) -> bytes   (used by /api/generate/zip)
    CLI: python -m gen.project_export <project_name> [--output DIR]
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from engine.project import Project, load_project

from . import can_h7, ecu_glue
from .generate import run_generators
from .stage import stage_project

# Resolve the source paths once. Honour OPENVINCI_VENDOR_AS the same
# way gen.generate does — keeps PyInstaller bundles happy.
import os

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENDOR_AS = Path(
    os.environ.get("OPENVINCI_VENDOR_AS")
    or (_REPO_ROOT / "vendor" / "as")
)
_HARDWARE_DIR = _REPO_ROOT / "hardware" / "stm32h753zi"
_TEMPLATES_DIR = _HARDWARE_DIR / "templates"

# autoas BSW C sources copied into bsw/. The list mirrors the in-repo
# hardware/stm32h753zi/Makefile's BSW_C — touching this here without
# touching the Makefile.export would break the link.
_BSW_C_RELS: tuple[str, ...] = (
    "infras/communication/Com/Com.c",
    "infras/communication/PduR/PduR.c",
    "infras/communication/PduR/PduR_Com.c",
    "infras/communication/PduR/PduR_CanIf.c",
    "infras/communication/CanIf/CanIf.c",
    "infras/mcal/Can/Can.c",
    "infras/libraries/stdbit/src/std_bit.c",
    "infras/libraries/mempool/mempool.c",
)

# BSW directories whose .h files we copy. The vendor C sources include
# headers from each of these dirs; matching what Makefile.export's
# BSW_INC -I flags list keeps the export consistent.
_BSW_INCLUDE_DIRS: tuple[str, ...] = (
    "infras/include",
    "infras/mcal/Can",
    "infras/communication/Com",
    "infras/communication/CanIf",
    "infras/communication/PduR",
    "infras/libraries/stdbit/src",
    "infras/libraries/mempool",
)

# CMSIS files. The exported project's Makefile expects:
#   third_party/CMSIS_5/CMSIS/Core/Include/*.h
#   third_party/cmsis-device-h7/Include/*.h
#   third_party/cmsis-device-h7/Source/Templates/system_stm32h7xx.c
#   third_party/cmsis-device-h7/Source/Templates/gcc/startup_stm32h753xx.s
_CMSIS_CORE_DIR = "third_party/CMSIS_5/CMSIS/Core/Include"
_CMSIS_DEV_INCLUDE = "third_party/cmsis-device-h7/Include"
_CMSIS_DEV_SYS_C = "third_party/cmsis-device-h7/Source/Templates/system_stm32h7xx.c"
_CMSIS_DEV_STARTUP_S = (
    "third_party/cmsis-device-h7/Source/Templates/gcc/startup_stm32h753xx.s"
)

# In-repo locations of the CMSIS submodules. The exported project
# copies subsets of these — we use the firmware tree's already-checked-
# out copies as the source of truth.
_LOCAL_CMSIS_CORE = _HARDWARE_DIR / "third_party" / "CMSIS_5" / "CMSIS" / "Core" / "Include"
_LOCAL_CMSIS_DEV = _HARDWARE_DIR / "third_party" / "cmsis-device-h7"

# Fixed template assets copied verbatim into the export. Format:
#   (source_path_relative_to_HARDWARE_DIR, dest_path_relative_to_export_root)
_FIXED_ASSETS: tuple[tuple[str, str], ...] = (
    ("src/Can_H7.c", "src/Can_H7.c"),
    ("src/system_init.c", "src/system_init.c"),
    ("src/board.c", "src/board.c"),
    ("include/board.h", "include/board.h"),
    ("linker/stm32h753xx_flash.ld", "linker/stm32h753xx_flash.ld"),
)


@dataclass(frozen=True)
class ExportResult:
    """Bookkeeping for the assembly step."""

    output_dir: Path
    written: list[Path]
    project_label: str


def _project_label(project: Project, source_dir: Path | None) -> str:
    """Best-guess display name. source_dir wins (it's the canonical
    name), else fall back to a Com network name, else 'project'."""
    if source_dir is not None:
        return source_dir.name
    if project.com is not None and project.com.networks:
        return project.com.networks[0].name
    return "project"


def _safe_project_slug(label: str) -> str:
    """Lowercase + replace anything non-alphanumeric with `-`. Used
    for the binary name so generated projects produce nicely-named
    .elf / .bin output."""
    import re

    slug = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-").lower()
    return slug or "project"


def _copy_tree_filtered(src: Path, dst: Path, *, suffixes: tuple[str, ...]) -> list[Path]:
    """shutil.copytree's `ignore` argument is awkward; just walk it.
    Returns the list of destination files written.
    """
    written: list[Path] = []
    for srcpath in src.rglob("*"):
        if not srcpath.is_file():
            continue
        if srcpath.suffix not in suffixes:
            continue
        rel = srcpath.relative_to(src)
        dstpath = dst / rel
        dstpath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(srcpath, dstpath)
        written.append(dstpath)
    return written


# -------------------------- README emission -------------------------


def _readme_text(project_label: str, project_slug: str, tx_signal: str | None, rx_signal: str | None) -> str:
    signals_block = ""
    if tx_signal and rx_signal:
        signals_block = (
            "\n"
            f"This project's Com signals (in `examples/{project_label}` /\n"
            f"`config/Com/Com.json`):\n"
            f"\n"
            f"- **{tx_signal}** — transmitted via "
            f"`Com_SendSignal(COM_SID_{tx_signal}, &value)`.\n"
            f"- **{rx_signal}** — received via "
            f"`Com_ReceiveSignal(COM_SID_{rx_signal}, &value)`.\n"
            f"\n"
            f"The generated `App_Demo.c` already drives these — replace it\n"
            f"with your own `App.c` once you wire your real application.\n"
        )
    return f"""\
# {project_label} — STM32H753ZI firmware (OpenVinci export)

GENERATED by OpenVinci. This folder is **self-contained**: every
source the link needs is here. No external repos or submodules to
fetch.

## What's inside

```
.
├── README.md              this file
├── Makefile               cross-build, self-contained paths
├── linker/                stm32h753xx_flash.ld
├── src/                   fixed templates
│   ├── Can_H7.c           FDCAN1 backend (table-driven)
│   ├── system_init.c      PLL2Q → 80 MHz FDCAN kernel clock
│   └── board.c            USART3 VCP + newlib stubs
├── include/board.h        board.c's public surface
├── generated/             OpenVinci-emitted *_Cfg.* + EcuM/Sched/App
├── bsw/                   autoas/as BSW sources (Com / PduR /
│                          CanIf / mcal-Can + libraries)
└── third_party/           CMSIS device + Core headers + startup
```

## Build

You need `arm-none-eabi-gcc` (Debian/Ubuntu: `apt install
gcc-arm-none-eabi`). Then:

```sh
make                       # → build/{project_slug}.{{elf,bin,hex}}
make size                  # arm-none-eabi-size summary
```

The default link uses the generated `EcuM.c` as `main()` and
`App_Demo.c` for `App_Init / App_MainFunction`. To run your own
application code, drop in your `App.c` implementing those two hooks
and remove `App_Demo.c` from the Makefile's `GLUE_C`.

## Flash + watch

```sh
make flash                 # st-link tools: `st-flash write … 0x8000000`
make flash-openocd         # OpenOCD: interface/stlink.cfg + target/stm32h7x.cfg
```

The on-board ST-LINK exposes a USB CDC Virtual COM Port at **115200
8N1, no flow control**. With the demo App running you should see:

```
openvinci-h7: boot (generated glue)
openvinci-h7: BSW initialized
openvinci-h7: scheduler running
openvinci-h7: app demo starting
openvinci-h7: RX=0x56
openvinci-h7: RX=0x57
...
```

(`RX=0xNN` comes from FDCAN1 internal-loopback echoing every TxSignal
straight back as an RxSignal.)
{signals_block}
## Customising

- **App code** — replace `generated/App_Demo.c` with your own file
  implementing `App_Init()` and `App_MainFunction()`.
- **Tick rate** — `generated/Sched.h` defines
  `OPENVINCI_TICK_PERIOD_MS`. Re-export with a different value via
  `tick_period_ms` if 1 ms is too fast.
- **Board** — `src/board.c` / `include/board.h` is the only
  board-specific code. Swap pins / baud / LEDs here.

## What's NOT here

- A CAN transceiver. The default firmware runs FDCAN1 in **internal
  loopback** (`CCCR.MON | TEST.LBCK`) so it works on a bare
  Nucleo-H753ZI. Plug in a transceiver (e.g. SN65HVD230) and remove
  the `fdcan_enable_internal_loopback()` call from `Can_H7.c` to
  send / receive real frames.
- FD frames. Classic CAN only (DLC ≤ 8). FD support is a future
  iteration.
"""


# ------------------------- main assembly ----------------------------


def assemble_h7_project(
    project: Project,
    output_dir: Path,
    *,
    source_dir: Path | None = None,
) -> ExportResult:
    """Assemble a complete, buildable STM32H7 firmware project.

    `output_dir` is wiped and recreated, then populated with:
        Makefile, README.md, src/, include/, linker/, generated/,
        bsw/, third_party/.

    Raises ValueError if the project doesn't have `target=stm32h753zi`
    in its project.json. (Or rather, this generator only knows how to
    assemble that target — callers should check first.)
    """
    output_dir = Path(output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    label = _project_label(project, source_dir)
    slug = _safe_project_slug(label)
    written: list[Path] = []

    # ---- 1. Run the existing generator pipeline into a temp staging
    # ----    dir, then copy the *_Cfg.{c,h} into the export's
    # ----    generated/ (just the .c/.h, not the staging artefacts).
    gen_dst = output_dir / "generated"
    gen_dst.mkdir()
    with tempfile.TemporaryDirectory(prefix="openvinci-export-") as stage_root:
        stage_dir = Path(stage_root)
        stage_project(project, stage_dir, source_dir=source_dir)
        vendor_outputs = run_generators(stage_dir)
        for src in vendor_outputs:
            if src.suffix not in {".c", ".h"}:
                continue
            text = src.read_text()
            # Strip the per-run timestamp the vendor generator stamps
            # — same normalisation regenerate.py does so re-exports
            # produce diff-stable output.
            import re

            text = re.sub(
                r"^\s*\*\s*Generated at .*\r?\n",
                "",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            dst = gen_dst / src.name
            dst.write_text(text)
            written.append(dst)

    # ---- 2. STM32H7 driver-config (PROMPT C2) ----
    written.extend(can_h7.generate(project, gen_dst))

    # ---- 3. Integration glue (PROMPT C3) ----
    written.extend(ecu_glue.generate(project, gen_dst))

    # ---- 4. Fixed template assets (driver, board, linker) ----
    for src_rel, dst_rel in _FIXED_ASSETS:
        src = _HARDWARE_DIR / src_rel
        dst = output_dir / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(dst)

    # ---- 5. Makefile (template with project name substitution) ----
    mk_template = (_TEMPLATES_DIR / "Makefile.export").read_text()
    mk_text = mk_template.replace("{project}", slug)
    mk_path = output_dir / "Makefile"
    mk_path.write_text(mk_text)
    written.append(mk_path)

    # ---- 6. autoas BSW sources + headers (vendor/as → bsw/) ----
    bsw_dst = output_dir / "bsw"
    for rel in _BSW_C_RELS:
        src = _VENDOR_AS / rel
        # Drop the leading "infras/" so the export's bsw/ mirrors the
        # vendor layout *without* the "infras" prefix — see Makefile.export.
        # Actually keep it: Makefile.export uses bsw/communication/...,
        # bsw/mcal/..., bsw/libraries/... — which all start under
        # infras/ in vendor/as. So strip "infras/" once.
        rel_in_export = rel[len("infras/") :] if rel.startswith("infras/") else rel
        dst = bsw_dst / rel_in_export
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(dst)

    for inc_dir_rel in _BSW_INCLUDE_DIRS:
        src_dir = _VENDOR_AS / inc_dir_rel
        rel_in_export = (
            inc_dir_rel[len("infras/") :]
            if inc_dir_rel.startswith("infras/")
            else inc_dir_rel
        )
        dst_dir = bsw_dst / rel_in_export
        written.extend(
            _copy_tree_filtered(src_dir, dst_dir, suffixes=(".h",))
        )

    # ---- 7. CMSIS (cmsis-device-h7 + CMSIS_5/Core) ----
    # Subset enough to compile: device headers + system_stm32h7xx.c +
    # gcc startup + Cortex-M core headers.
    written.extend(
        _copy_tree_filtered(
            _LOCAL_CMSIS_DEV / "Include",
            output_dir / _CMSIS_DEV_INCLUDE,
            suffixes=(".h",),
        )
    )
    sys_c_src = _LOCAL_CMSIS_DEV / "Source" / "Templates" / "system_stm32h7xx.c"
    sys_c_dst = output_dir / _CMSIS_DEV_SYS_C
    sys_c_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sys_c_src, sys_c_dst)
    written.append(sys_c_dst)

    startup_src = (
        _LOCAL_CMSIS_DEV / "Source" / "Templates" / "gcc" / "startup_stm32h753xx.s"
    )
    startup_dst = output_dir / _CMSIS_DEV_STARTUP_S
    startup_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(startup_src, startup_dst)
    written.append(startup_dst)

    written.extend(
        _copy_tree_filtered(
            _LOCAL_CMSIS_CORE,
            output_dir / _CMSIS_CORE_DIR,
            suffixes=(".h",),
        )
    )

    # ---- 8. README ----
    tx_sig: str | None = None
    rx_sig: str | None = None
    if project.com is not None:
        for net in project.com.networks:
            for msg in net.messages or []:
                for sig in msg.signals or []:
                    receivers = (
                        sig.node if isinstance(sig.node, list) else [sig.node]
                    )
                    if net.me in receivers and rx_sig is None:
                        rx_sig = sig.name
                    elif net.me not in receivers and tx_sig is None:
                        tx_sig = sig.name
    readme = output_dir / "README.md"
    readme.write_text(_readme_text(label, slug, tx_sig, rx_sig))
    written.append(readme)

    return ExportResult(output_dir=output_dir, written=written, project_label=label)


# -------------------------- zip wrapper -----------------------------


def write_zip(
    project: Project,
    *,
    source_dir: Path | None = None,
) -> tuple[bytes, str]:
    """Assemble the export into a temp dir, zip it up STORED, return
    `(bytes, label)`. The caller (HTTP layer) wraps that in a
    StreamingResponse.
    """
    with tempfile.TemporaryDirectory(prefix="openvinci-export-zip-") as tmp:
        out = Path(tmp) / "export"
        result = assemble_h7_project(project, out, source_dir=source_dir)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            for p in result.written:
                # arcname rooted at the project label so unzipping
                # gives you `openvinci-<label>/...` rather than a
                # bare loose-file dump.
                rel = p.relative_to(out)
                zf.write(p, arcname=str(Path(result.project_label) / rel))
        return buf.getvalue(), result.project_label


# ------------------------------ CLI ---------------------------------


def _cli() -> int:
    """`python -m gen.project_export <name> [--output DIR]` exports a
    named example project to DIR (default: ./openvinci-<name>/). Used
    by CI to verify the export actually compiles."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Export a complete, buildable STM32H753ZI project."
    )
    parser.add_argument(
        "project",
        help="examples/<name>/ project to export (must have project.json "
        "target=stm32h753zi).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Destination directory (default: ./openvinci-<name>/).",
    )
    args = parser.parse_args()

    examples_root = _REPO_ROOT / "examples"
    src = examples_root / args.project
    if not src.is_dir():
        print(f"examples/{args.project} not found at {src}", file=sys.stderr)
        return 2
    if not can_h7.is_h7_target(src):
        print(
            f"examples/{args.project}/project.json doesn't select target=stm32h753zi",
            file=sys.stderr,
        )
        return 2

    out = args.output or Path.cwd() / f"openvinci-{args.project}"
    project = load_project(src)
    result = assemble_h7_project(project, out, source_dir=src)
    print(f"exported {len(result.written)} files to {result.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
