"""Generation must succeed even when no C toolchain is on PATH.

The desktop launcher (D1) and any clean-machine pip install live or
die by this contract: importing a DBC, generating the skeleton, and
saving the files MUST NOT depend on having gcc available — only the
optional compile verification does. This module verifies it.

We test at three levels so a regression at any one of them stays
visible:

  1. `compile_check` returns status="unavailable" cleanly when gcc
     isn't on PATH (no exception, no 500).
  2. `generate_and_compile` against examples/com-minimal still
     produces every expected *_Cfg.c — generation doesn't even shell
     out to gcc.
  3. The /api/generate HTTP endpoint surfaces compileResult.status
     == "unavailable" rather than dropping the request on the floor.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from engine import load_project
from gen import generate_and_compile
from gen.compile import compile_check

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def no_toolchain_path(monkeypatch):
    """Mask gcc on PATH for the duration of a test.

    We don't blank PATH entirely — that breaks every other tool the
    backend might call. Instead we point PATH at a scratch directory
    that contains nothing named `gcc`, then monkey-patch shutil.which
    inside the gen.compile module so the lookup honours the trimmed
    PATH even if pytest is running from a venv where shutil caches a
    different result.
    """
    empty_bin = REPO_ROOT / "build" / "no-toolchain-bin"
    empty_bin.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PATH", str(empty_bin))
    # Sanity — without this assertion a future Python change to
    # shutil.which() caching could silently pass the tests.
    assert shutil.which("gcc") is None, (
        "shutil.which('gcc') still resolves with PATH set to "
        f"{empty_bin!r} — something on the test runner is leaking "
        "a toolchain directory back in."
    )
    return empty_bin


# --- unit: compile_check --------------------------------------------


def test_compile_check_returns_unavailable_when_gcc_missing(
    tmp_path: Path, no_toolchain_path
):
    """No subprocess spawned at all when shutil.which returns None —
    we return the skip result up-front."""
    fake_c = tmp_path / "fake.c"
    fake_c.write_text("int main(void){return 0;}\n")
    result = compile_check(tmp_path, [fake_c])
    assert result.status == "unavailable"
    # A single `note` message, never `error` — this isn't a failure,
    # it's a deliberate skip the UI should render in info-blue.
    assert all(m.severity == "note" for m in result.messages)
    assert len(result.messages) == 1
    assert "no c toolchain" in result.messages[0].message.lower()
    # The representative command is still populated so the user can
    # see what would have run.
    assert result.command[0] in ("gcc", "cc")


def test_compile_check_unavailable_works_even_with_zero_c_files(
    tmp_path: Path, no_toolchain_path
):
    """An empty c_files list still reports unavailable rather than ok —
    we don't want to silently mark a no-gcc run as "verified clean"."""
    result = compile_check(tmp_path, [])
    assert result.status == "unavailable"


# --- integration: generate_and_compile -------------------------------


def test_generate_succeeds_without_toolchain_against_com_minimal(
    tmp_path: Path, no_toolchain_path
):
    """The headline claim: import-and-generate still produces the
    same *_Cfg.c files on a clean machine; only verification is
    skipped."""
    project = load_project(REPO_ROOT / "examples" / "com-minimal")
    result = generate_and_compile(
        project, tmp_path, source_dir=REPO_ROOT / "examples" / "com-minimal"
    )

    # Generation produced the canonical L1 outputs.
    paths = {f.path for f in result.files}
    for stem in ("Com_Cfg.c", "CanIf_Cfg.c", "PduR_Cfg.c"):
        assert any(p.endswith(stem) for p in paths), (
            f"missing {stem}; generated set was {sorted(paths)}"
        )

    # The compile step degraded gracefully.
    cr = result.compile_result
    assert cr is not None
    assert cr.status == "unavailable"
    assert any(
        "no c toolchain" in m.message.lower() for m in cr.messages
    ), [m.message for m in cr.messages]


# --- HTTP: /api/generate ---------------------------------------------


def test_api_generate_returns_unavailable_status_without_gcc(
    no_toolchain_path,
):
    """End-to-end through the API surface: the UI consumes this shape
    and is expected to render "verification unavailable" rather than
    "errors". A 200 here is the contract."""
    client = TestClient(app)
    response = client.post("/api/generate", params={"project": "com-minimal"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["files"], "generation produced zero files"
    assert body["compileResult"] is not None
    assert body["compileResult"]["status"] == "unavailable"


def test_api_generate_zip_works_without_gcc(no_toolchain_path):
    """The zip retrieval path is the primary value-add for hosted
    users; it MUST NOT depend on the toolchain being present.
    Equivalent of pressing "Download .zip" right after an Import DBC
    on a freshly-installed desktop app."""
    client = TestClient(app)
    response = client.post(
        "/api/generate/zip", params={"project": "com-minimal"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    assert response.content[:4] == b"PK\x03\x04"  # zip local-file-header
