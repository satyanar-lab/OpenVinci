"""Guard the contract that `hardware/` is isolated from the web app.

PROMPT H1 specifies: the embedded-firmware area MUST NOT be referenced
or bundled by the Python package, the Dockerfile, the PyInstaller
desktop.spec, scripts/verify.sh, or the top-level Makefile's main
targets. These tests are the regression bumper that catches an
accidental `COPY hardware/` or `datas=[..., "hardware/..."]` in a
future PR.

Pure file-IO assertions. Cheap to run in CI; no toolchain required.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.relative_to(REPO_ROOT)} not present in this checkout")
    return path.read_text()


def test_backend_pyproject_does_not_package_hardware():
    """`backend/pyproject.toml` allowlists which sub-packages get
    installed; `hardware*` MUST NOT appear in that list (it isn't
    Python anyway). A glob like `*` would silently sweep it in — the
    explicit allowlist is the safer shape."""
    text = _read(REPO_ROOT / "backend" / "pyproject.toml")
    # Sanity: the allowlist exists.
    assert "[tool.setuptools.packages.find]" in text
    # And it doesn't mention hardware.
    assert "hardware" not in text.lower(), (
        "backend/pyproject.toml mentions 'hardware'; the embedded-"
        "firmware tree must stay out of the Python package layout."
    )


def test_dockerignore_excludes_hardware_tree():
    """.dockerignore drops `hardware/` from the build context so the
    big CMSIS_5 submodule (~150 MB unpacked) doesn't bloat docker
    builds — and so an accidental `COPY hardware/` in the Dockerfile
    would copy nothing."""
    text = _read(REPO_ROOT / ".dockerignore")
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    # Either `hardware/` or `hardware` (with or without trailing slash)
    # both work in dockerignore. Accept either.
    assert "hardware/" in lines or "hardware" in lines, (
        ".dockerignore must list 'hardware/' to keep the embedded "
        "firmware out of the Docker image."
    )


def test_dockerfile_does_not_reference_hardware():
    """The Dockerfile must not COPY / ADD / mention hardware/. Its
    only COPY lines are model/, examples/, scripts/, tests/,
    backend/, vendor/as/, and the built frontend dist."""
    text = _read(REPO_ROOT / "Dockerfile")
    assert "hardware" not in text.lower(), (
        "Dockerfile references 'hardware' — the embedded firmware "
        "must not be part of the Docker image."
    )


def test_pyinstaller_spec_does_not_bundle_hardware():
    """`desktop.spec`'s `datas=[...]` lists the dirs PyInstaller
    bundles into _MEIPASS. `hardware/` must not be one of them."""
    text = _read(REPO_ROOT / "desktop.spec")
    assert "hardware" not in text.lower(), (
        "desktop.spec references 'hardware' — the PyInstaller bundle "
        "must not include the embedded firmware tree."
    )


def test_verify_sh_does_not_reference_hardware():
    """`scripts/verify.sh` runs the host verification suite. It must
    not touch hardware/ — embedded-firmware checks belong on real
    silicon, not in the host CI."""
    text = _read(REPO_ROOT / "scripts" / "verify.sh")
    assert "hardware" not in text.lower(), (
        "scripts/verify.sh references 'hardware' — embedded firmware "
        "must stay out of the host verification report."
    )


def test_top_level_makefile_isolates_hardware_targets():
    """The top-level Makefile's main targets (build, run, dev,
    desktop, desktop-app, test, verify) must not depend on or
    reference hardware/. A cross-build is opt-in from inside
    `hardware/stm32h753zi/` only."""
    text = _read(REPO_ROOT / "Makefile")
    # Strip comments so a future explanatory comment about hardware/
    # in the makefile doesn't trip this.
    code = "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("#")
    )
    assert "hardware" not in code.lower(), (
        "Top-level Makefile references 'hardware' outside comments — "
        "embedded firmware build must stay opt-in via "
        "`cd hardware/stm32h753zi && make`."
    )


@pytest.mark.parametrize(
    "path",
    [
        "hardware/stm32h753zi/README.md",
        "hardware/stm32h753zi/Makefile",
        "hardware/stm32h753zi/src/main.c",
        "hardware/stm32h753zi/linker/stm32h753xx_flash.ld",
    ],
)
def test_hardware_files_exist(path: str):
    """Sanity: the firmware area lives where the README says it does.
    A `path not found` here means a refactor moved things and the
    isolation tests above might be testing the wrong tree."""
    assert (REPO_ROOT / path).is_file(), f"missing: {path}"


def test_gitmodules_lists_h753zi_submodules():
    """`.gitmodules` must record the cmsis-device-h7 + CMSIS_5
    submodules so `git submodule update --init` (or
    `--init --recursive` from the top) brings them in."""
    text = _read(REPO_ROOT / ".gitmodules")
    assert re.search(
        r'\[submodule\s+"hardware/stm32h753zi/third_party/cmsis-device-h7"\]',
        text,
    ), ".gitmodules missing hardware/stm32h753zi/third_party/cmsis-device-h7"
    assert re.search(
        r'\[submodule\s+"hardware/stm32h753zi/third_party/CMSIS_5"\]',
        text,
    ), ".gitmodules missing hardware/stm32h753zi/third_party/CMSIS_5"


# --- PROMPT FIX: positive assertions for the h7_template -------------
#
# The export-template assets (backend/gen/h7_template/) DO ship in the
# backend package and the desktop bundle — that's how the H7 export
# works in the Docker image and the desktop app even though the
# embedded-firmware tree is excluded. These tests pin the contract so
# a future "let's drop package_data" PR has to remove the assertion
# explicitly.


def test_pyproject_packages_the_h7_template():
    """The backend package_data MUST enumerate the H7 template files
    — without this, `pip install -e backend` skips them and
    `project_export.assemble_h7_project` raises FileNotFoundError at
    runtime in the Docker image."""
    text = _read(REPO_ROOT / "backend" / "pyproject.toml")
    assert "[tool.setuptools.package-data]" in text, (
        "backend/pyproject.toml is missing the package-data section "
        "that ships gen/h7_template/."
    )
    for tracked in (
        "h7_template/Makefile.export",
        "h7_template/src/*.c",
        "h7_template/linker/*.ld",
        "h7_template/third_party/cmsis-device-h7/Include/*.h",
        "h7_template/third_party/CMSIS_5/CMSIS/Core/Include/*.h",
    ):
        assert tracked in text, f"package-data missing {tracked!r}"


def test_desktop_spec_bundles_the_h7_template():
    """The PyInstaller bundle includes gen/h7_template so the
    desktop H7 export reads from the bundled subset, not the
    embedded-firmware tree (which the bundle excludes)."""
    text = _read(REPO_ROOT / "desktop.spec")
    assert "backend/gen/h7_template" in text, (
        "desktop.spec must add backend/gen/h7_template → gen/h7_template "
        "to its datas list."
    )


def test_h7_template_only_ships_h753_device_headers():
    """The export only needs three device headers (the dispatcher
    stm32h7xx.h, the H753 device header, and system_stm32h7xx.h).
    Pulling in all 24 family device headers would bloat the Python
    package by ~46 MB for code paths the H7 build never compiles."""
    template_inc = (
        REPO_ROOT / "backend" / "gen" / "h7_template"
        / "third_party" / "cmsis-device-h7" / "Include"
    )
    if not template_inc.is_dir():
        pytest.skip(
            "backend/gen/h7_template not populated in this checkout."
        )
    headers = sorted(p.name for p in template_inc.glob("*.h"))
    assert headers == sorted(
        ["stm32h7xx.h", "stm32h753xx.h", "system_stm32h7xx.h"]
    ), (
        "h7_template's cmsis-device-h7 Include set drifted — the H7 "
        f"export build needs only three device headers; got {headers}."
    )


def test_dockerfile_does_not_pull_cmsis_5_submodule_into_image():
    """The bundled trimmed CMSIS subset under gen/h7_template/ is
    ~3 MB. The full CMSIS_5 submodule (DSP, RTOS2, NN, etc.) is
    ~150 MB and has no place in the image. The Dockerfile MUST NOT
    copy or reference the in-repo CMSIS_5 path directly — it gets the
    small subset for free via backend/gen/h7_template/, which is part
    of the backend package."""
    text = _read(REPO_ROOT / "Dockerfile")
    forbidden = (
        "CMSIS_5/CMSIS/DSP",
        "CMSIS_5/CMSIS/NN",
        "CMSIS_5/CMSIS/RTOS",
        "third_party/CMSIS_5\n",
        "third_party/CMSIS_5 ",
    )
    for token in forbidden:
        assert token not in text, (
            f"Dockerfile references {token!r} — that would pull the "
            "~150 MB CMSIS_5 submodule into the image."
        )
