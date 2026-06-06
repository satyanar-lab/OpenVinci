"""Bundle-mode path-resolution overrides.

A PyInstaller bundle (or any sandboxed install) sets the OPENVINCI_*
env vars BEFORE the backend is imported, so the backend reads its
schemas / examples / vendor-as from the bundle's extracted data dir
instead of relative-to-`__file__` (which would point at a temp dir
inside the bundle). These tests verify the override hooks honour the
contract that the desktop launcher relies on.

Strictly unit-level — they don't require PyInstaller or the bundle.
The full bundle smoke-test is manual; see README "Build a double-click
bundle".
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

# `desktop` lives at the repo root, not inside backend/, so add the
# repo root to sys.path explicitly. Mirrors what the test_desktop_
# launcher.py module already does.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Tests in this file mutate OPENVINCI_* env vars via
# os.environ.setdefault, which pytest's monkeypatch does NOT track.
# Without this autouse cleanup the leaked vars cascade into every
# subsequent test in the session — e.g. test_schemas.py loads schemas
# from `OPENVINCI_SCHEMAS_DIR` and would suddenly see a tmp_path that
# was wiped at the end of the test that set it.
_BUNDLE_ENV_KEYS = (
    "OPENVINCI_FRONTEND_DIST",
    "OPENVINCI_EXAMPLES_DIR",
    "OPENVINCI_SCHEMAS_DIR",
    "OPENVINCI_VENDOR_AS",
)


@pytest.fixture(autouse=True)
def _cleanup_bundle_env():
    """Snapshot the four bundle env vars before each test, restore
    them after. Catches anything `os.environ.setdefault` slips past
    monkeypatch."""
    snapshot = {k: os.environ.get(k) for k in _BUNDLE_ENV_KEYS}
    yield
    for k, v in snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_vendor_as_env_override_honoured_by_compile(monkeypatch, tmp_path):
    """gen.compile reads OPENVINCI_VENDOR_AS at lookup time so the
    bundle can point it at _MEIPASS/vendor/as without code edits."""
    fake_vendor = tmp_path / "fake-vendor-as"
    (fake_vendor / "infras" / "include").mkdir(parents=True)
    monkeypatch.setenv("OPENVINCI_VENDOR_AS", str(fake_vendor))

    # _vendor_as / include_dirs_for read the env every call — no
    # reload dance required.
    from gen.compile import _vendor_as, include_dirs_for

    assert _vendor_as() == fake_vendor
    incs = include_dirs_for(tmp_path)
    assert incs[0] == fake_vendor / "infras" / "include"


def test_vendor_as_env_override_honoured_by_generate(monkeypatch, tmp_path):
    """gen.generate's _vendor_as_tools picks up the same env var, so
    `import generator` resolves to the bundle's extracted tree."""
    fake_vendor = tmp_path / "fake-vendor-as"
    (fake_vendor / "tools").mkdir(parents=True)
    monkeypatch.setenv("OPENVINCI_VENDOR_AS", str(fake_vendor))

    from gen.generate import _vendor_as_tools

    assert _vendor_as_tools() == fake_vendor / "tools"


def test_schemas_dir_env_override_honoured_by_engine(monkeypatch, tmp_path):
    """engine.validate's _model_dir reads OPENVINCI_SCHEMAS_DIR. The
    desktop launcher sets this BEFORE importing app.main so the
    schemas resolve under _MEIPASS, not REPO_ROOT."""
    fake_model = tmp_path / "fake-model"
    fake_model.mkdir()
    monkeypatch.setenv("OPENVINCI_SCHEMAS_DIR", str(fake_model))

    from engine.validate import _model_dir

    assert _model_dir() == fake_model


def test_desktop_set_bundle_paths_no_op_in_source_mode(monkeypatch):
    """When sys.frozen is unset (source-tree run), _set_bundle_paths
    must NOT set any OPENVINCI_* env vars — overriding the source-mode
    defaults to the bundle path would break local dev."""
    import sys

    import desktop.app as da

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    # Clear any pre-existing env vars so we can prove _set_bundle_paths
    # didn't add them.
    for key in (
        "OPENVINCI_FRONTEND_DIST",
        "OPENVINCI_EXAMPLES_DIR",
        "OPENVINCI_SCHEMAS_DIR",
        "OPENVINCI_VENDOR_AS",
    ):
        monkeypatch.delenv(key, raising=False)

    da._set_bundle_paths()  # no-op

    import os
    assert "OPENVINCI_FRONTEND_DIST" not in os.environ
    assert "OPENVINCI_SCHEMAS_DIR" not in os.environ
    assert "OPENVINCI_VENDOR_AS" not in os.environ


def test_desktop_set_bundle_paths_uses_meipass_when_frozen(monkeypatch, tmp_path):
    """When sys.frozen is set, _set_bundle_paths points the backend at
    sys._MEIPASS via OPENVINCI_* env vars. This is the bundle's main
    init step — without it, a frozen `from app.main import app` would
    crash on the engine.validate registry load."""
    import sys

    import desktop.app as da

    fake_bundle = tmp_path / "fake-meipass"
    fake_bundle.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_bundle), raising=False)
    for key in (
        "OPENVINCI_FRONTEND_DIST",
        "OPENVINCI_EXAMPLES_DIR",
        "OPENVINCI_SCHEMAS_DIR",
        "OPENVINCI_VENDOR_AS",
    ):
        monkeypatch.delenv(key, raising=False)

    da._set_bundle_paths()

    import os
    assert os.environ["OPENVINCI_FRONTEND_DIST"] == str(
        fake_bundle / "frontend" / "dist"
    )
    assert os.environ["OPENVINCI_EXAMPLES_DIR"] == str(fake_bundle / "examples")
    assert os.environ["OPENVINCI_SCHEMAS_DIR"] == str(fake_bundle / "model")
    assert os.environ["OPENVINCI_VENDOR_AS"] == str(
        fake_bundle / "vendor" / "as"
    )


def test_desktop_set_bundle_paths_respects_existing_env(
    monkeypatch, tmp_path
):
    """User-supplied env vars MUST win over the bundle defaults so
    `OPENVINCI_EXAMPLES_DIR=/somewhere ./OpenVinci` lets the user point
    the bundle at an external project dir without recompiling."""
    import sys

    import desktop.app as da

    fake_bundle = tmp_path / "fake-meipass"
    fake_bundle.mkdir()
    user_examples = tmp_path / "user-projects"
    user_examples.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_bundle), raising=False)
    # `_set_bundle_paths` uses os.environ.setdefault, so any value
    # already present at call time wins. Clear the rest so we can
    # compare against the bundle defaults this call writes.
    for key in (
        "OPENVINCI_FRONTEND_DIST",
        "OPENVINCI_SCHEMAS_DIR",
        "OPENVINCI_VENDOR_AS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENVINCI_EXAMPLES_DIR", str(user_examples))

    da._set_bundle_paths()

    import os
    assert os.environ["OPENVINCI_EXAMPLES_DIR"] == str(user_examples)
    # The other ones should fall back to the bundle defaults.
    assert os.environ["OPENVINCI_VENDOR_AS"] == str(
        fake_bundle / "vendor" / "as"
    )
