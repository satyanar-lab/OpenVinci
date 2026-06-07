"""Guard the contract between hardware/stm32h753zi/ (canonical source)
and backend/gen/h7_template/ (the runtime copy the project_export
generator reads from).

Why two copies exist
--------------------

`hardware/stm32h753zi/` is the in-repo embedded-firmware area. It's
the place humans edit when changing the FDCAN driver, the board
helpers, the linker script, or the Makefile template. PROMPT FIX
deliberately keeps it as the canonical source.

`backend/gen/h7_template/` is a vendored MIRROR of just the files
`project_export.py` needs at runtime. It ships inside the Python
package (`backend[gen]` package_data) and inside the desktop
PyInstaller bundle, so the H7 export works in the Docker image and
the desktop app — both of which deliberately exclude `hardware/`.

The risk is silent drift: an edit to `hardware/stm32h753zi/src/Can_H7.c`
that doesn't land in `backend/gen/h7_template/src/Can_H7.c` would
ship a different driver to web/desktop users than the one developers
test on the bench. This test catches that.

How
---

For every file the export ships, we byte-compare the in-template copy
against the in-repo source. The CMSIS subset is special: the device
header set is intentionally trimmed (only stm32h7xx + stm32h753xx +
system_stm32h7xx — the other 21 family device headers sit in
`#elif` branches that don't fire under `-DSTM32H753xx`). So we check
that **every file present in the template is a byte-exact copy of the
corresponding in-repo file** — but we DON'T require the template to
mirror every file under hardware/.

When `hardware/` isn't checked out (e.g. an installed wheel in an
isolated CI runner) the test is skipped cleanly. That's correct: the
drift check is a development-time guarantee, not a runtime claim.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARDWARE_DIR = REPO_ROOT / "hardware" / "stm32h753zi"
TEMPLATE_DIR = REPO_ROOT / "backend" / "gen" / "h7_template"


def _require_hardware() -> None:
    if not HARDWARE_DIR.is_dir():
        pytest.skip(
            "hardware/stm32h753zi not present in this checkout — drift check "
            "is a dev-time guarantee only."
        )


# (template_rel, hardware_rel) pairs — symmetric across the canonical
# source and the runtime mirror. The dst inside the export is the same
# as the template's path (project_export.assemble_h7_project doesn't
# rename anything but the project-slug placeholder in Makefile.export).
_DRIVER_AND_BOARD_FILES: tuple[tuple[str, str], ...] = (
    ("src/Can_H7.c", "src/Can_H7.c"),
    ("src/system_init.c", "src/system_init.c"),
    ("src/board.c", "src/board.c"),
    ("include/board.h", "include/board.h"),
    ("linker/stm32h753xx_flash.ld", "linker/stm32h753xx_flash.ld"),
    ("Makefile.export", "templates/Makefile.export"),
)


@pytest.mark.parametrize("template_rel,hardware_rel", _DRIVER_AND_BOARD_FILES)
def test_driver_and_board_assets_match_hardware_source(
    template_rel: str, hardware_rel: str
):
    """Each fixed template asset MUST be byte-equal to its canonical
    source under hardware/stm32h753zi/. If you intentionally change
    one, sync the mirror — typically:

        cp hardware/stm32h753zi/<file> backend/gen/h7_template/<file>
    """
    _require_hardware()
    src = HARDWARE_DIR / hardware_rel
    dst = TEMPLATE_DIR / template_rel
    assert src.is_file(), f"missing canonical source: {hardware_rel}"
    assert dst.is_file(), (
        f"missing template mirror: {template_rel} — "
        "copy it from hardware/stm32h753zi/."
    )
    assert src.read_bytes() == dst.read_bytes(), (
        f"drift: backend/gen/h7_template/{template_rel} differs from "
        f"hardware/stm32h753zi/{hardware_rel}. "
        "Re-sync the mirror:\n"
        f"    cp hardware/stm32h753zi/{hardware_rel} backend/gen/h7_template/{template_rel}"
    )


def test_cmsis_subset_files_match_hardware_source():
    """CMSIS files present in the template subset must match
    hardware/'s authoritative checkout byte-for-byte. The template
    subset is intentionally smaller (only stm32h7xx.h /
    stm32h753xx.h / system_stm32h7xx.h from cmsis-device-h7) so
    we DO NOT assert symmetry — just that what's present matches."""
    _require_hardware()
    hw_cmsis_dev = HARDWARE_DIR / "third_party" / "cmsis-device-h7"
    hw_cmsis_core = (
        HARDWARE_DIR
        / "third_party"
        / "CMSIS_5"
        / "CMSIS"
        / "Core"
        / "Include"
    )
    template_cmsis_dev = TEMPLATE_DIR / "third_party" / "cmsis-device-h7"
    template_cmsis_core = (
        TEMPLATE_DIR / "third_party" / "CMSIS_5" / "CMSIS" / "Core" / "Include"
    )

    drift: list[str] = []
    # Compare every file present in the template subset against the
    # corresponding in-repo CMSIS source.
    for template_root, hardware_root in (
        (template_cmsis_dev, hw_cmsis_dev),
        (template_cmsis_core, hw_cmsis_core),
    ):
        if not template_root.is_dir():
            continue
        for tpl_path in template_root.rglob("*"):
            if not tpl_path.is_file():
                continue
            rel = tpl_path.relative_to(template_root)
            hw_path = hardware_root / rel
            if not hw_path.is_file():
                drift.append(
                    f"in template but not in hardware/: "
                    f"{tpl_path.relative_to(TEMPLATE_DIR)}"
                )
                continue
            if tpl_path.read_bytes() != hw_path.read_bytes():
                drift.append(
                    f"byte mismatch: {tpl_path.relative_to(TEMPLATE_DIR)} "
                    f"vs hardware/stm32h753zi/{hw_path.relative_to(HARDWARE_DIR)}"
                )
    assert not drift, (
        "CMSIS template drift:\n  " + "\n  ".join(drift)
    )


def test_template_cmsis_subset_is_intentionally_trimmed():
    """The full cmsis-device-h7 Include dir has 24 device headers
    (~46 MB). With `-DSTM32H753xx` the preprocessor only takes the
    H753 branch — the other 21 device headers are dead weight inside
    the backend package and the desktop bundle. PROMPT FIX trimmed
    them.

    This test documents the invariant so a future "let's just copy
    everything" PR has to explicitly remove the assertion.
    """
    template_inc = (
        TEMPLATE_DIR / "third_party" / "cmsis-device-h7" / "Include"
    )
    assert template_inc.is_dir(), "missing template cmsis-device-h7/Include"
    headers = sorted(p.name for p in template_inc.glob("*.h"))
    assert headers == sorted(
        ["stm32h7xx.h", "stm32h753xx.h", "system_stm32h7xx.h"]
    ), (
        "template cmsis-device-h7 Include drift — expected only the H753 "
        f"device header set; got: {headers}.\n"
        "If you need to add a device header to support another board "
        "target, do it deliberately AND extend the corresponding test."
    )
