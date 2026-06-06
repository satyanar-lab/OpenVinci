"""Desktop launcher helpers.

These tests exercise the server-start / wait-for-health / stop chain
of `desktop/app.py` without ever opening a pywebview window. They run
on headless CI by design — pywebview's GTK/QT backend isn't installed
on the runners, and the launcher's `--no-window` flow is the canonical
"server up, no UI" path anyway.

The full `python -m desktop.app` (with a real window) is a manual
smoke-test; the README's "Run as a desktop app" section documents it.
"""

from __future__ import annotations

import importlib
import socket
import threading
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_desktop_app():
    """Import desktop.app, making sure the repo root is on sys.path
    so the `desktop` package is reachable from inside the backend's
    pytest test config."""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    return importlib.import_module("desktop.app")


def test_find_free_port_returns_a_usable_loopback_port():
    da = _import_desktop_app()
    port = da.find_free_port()
    assert 1024 <= port <= 65535
    # The chosen port should be bindable a second time (kernel-assigned
    # ephemeral ports aren't reserved across calls — we want
    # confirmation that the helper's contract is just "free at the
    # moment", not "reserved").
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_start_server_then_wait_for_health_round_trip(tmp_path, monkeypatch):
    """The full launcher chain minus the window: pick a port, boot
    uvicorn in a thread, poll /health, hit an API endpoint, stop.
    This is what `python -m desktop.app --no-window` does."""
    # Build a stub dist so the SPA catch-all doesn't 503 on `/` —
    # the FastAPI app needs that even for /health.
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><html><body data-test='desktop'></body></html>"
    )
    monkeypatch.setenv("OPENVINCI_FRONTEND_DIST", str(dist))

    # Reload the backend app so it picks up the env var.
    import app.main as main_mod
    importlib.reload(main_mod)

    da = _import_desktop_app()
    port = da.find_free_port()
    server, thread = da.start_server(port)
    try:
        assert da.wait_for_health(port, timeout=10.0), (
            "uvicorn did not respond at /health within 10 s"
        )

        # The app is reachable; sanity-check that one of our real
        # routes also serves correctly (not just /health which is a
        # 4-line liveness probe).
        with urllib.request.urlopen(  # noqa: S310
            f"http://127.0.0.1:{port}/api/projects", timeout=2.0
        ) as r:
            assert r.status == 200
            body = r.read().decode("utf-8")
            assert '"projects"' in body
    finally:
        da.stop_server(server, thread)

    # Server thread should be dead within the join timeout.
    thread.join(timeout=2.0)
    assert not thread.is_alive(), "server thread did not exit after stop_server()"


def test_main_exits_2_when_frontend_dist_is_missing(monkeypatch, tmp_path, capsys):
    """The launcher refuses to start when the frontend bundle hasn't
    been built — desktop mode expects the SPA at /, not a 503."""
    da = _import_desktop_app()
    missing = tmp_path / "no-dist"
    monkeypatch.setattr(da, "FRONTEND_DIST", missing)
    rc = da.main(["--no-window", "--health-timeout", "1"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "frontend bundle missing" in err
    assert "make build" in err


def test_main_no_window_runs_and_exits_cleanly_when_thread_dies(
    tmp_path, monkeypatch
):
    """`--no-window` blocks until the server thread dies. Drive the
    happy path by tearing the server down from another thread after
    /health is up; main() must return 0."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    monkeypatch.setenv("OPENVINCI_FRONTEND_DIST", str(dist))
    import app.main as main_mod
    importlib.reload(main_mod)

    da = _import_desktop_app()

    # Patch FRONTEND_DIST so the launcher sees our scratch dir even
    # though the env var is the canonical knob in main_mod.
    monkeypatch.setattr(da, "FRONTEND_DIST", dist)

    captured: dict[str, object] = {}
    real_start = da.start_server

    def capturing_start(port: int, **kwargs):
        server, thread = real_start(port, **kwargs)
        captured["server"] = server
        captured["thread"] = thread
        return server, thread

    monkeypatch.setattr(da, "start_server", capturing_start)

    # Pick a port so we know which one to wait on without racing.
    port = da.find_free_port()
    monkeypatch.setattr(da, "find_free_port", lambda host="127.0.0.1": port)

    def killer():
        # Wait for the server to come up, then ask it to stop.
        for _ in range(200):  # up to 10 s
            if "server" in captured:
                break
            time.sleep(0.05)
        # Wait a beat so main() is inside the while loop.
        time.sleep(0.2)
        server = captured.get("server")
        if server is not None:
            server.should_exit = True  # type: ignore[union-attr]

    t = threading.Thread(target=killer, daemon=True)
    t.start()

    rc = da.main(["--no-window", "--port", str(port), "--health-timeout", "5"])
    assert rc == 0


def test_wait_for_health_times_out_quickly_on_bad_port():
    """A port nothing is listening on should fail fast — the polling
    loop has a short interval, the timeout argument is the real
    upper bound."""
    da = _import_desktop_app()
    # Pick a port, immediately release it. The window where nothing
    # is listening is what we test against. Tiny timeout keeps the
    # test snappy.
    port = da.find_free_port()
    t0 = time.time()
    ok = da.wait_for_health(port, timeout=0.3)
    assert ok is False
    assert time.time() - t0 < 2.0, "wait_for_health should respect the timeout"


def test_module_imports_without_pywebview_installed(monkeypatch):
    """pywebview is an OPTIONAL dependency — a server-only install
    that never opens a window must still be able to `import desktop.app`
    and call its helpers. We sabotage pywebview to confirm.
    """
    import sys

    monkeypatch.setitem(sys.modules, "webview", None)
    # The launcher imports webview lazily in _open_window, so all the
    # helpers we exercise above must still work without it.
    da = importlib.reload(_import_desktop_app())
    assert callable(da.find_free_port)
    assert callable(da.start_server)
    assert callable(da.wait_for_health)
    assert callable(da.stop_server)
