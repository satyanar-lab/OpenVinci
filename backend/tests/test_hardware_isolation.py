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
