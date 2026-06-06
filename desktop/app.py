"""Desktop launcher — boot uvicorn + open a pywebview window.

The same FastAPI app the hosted flow serves runs here, point-blank.
We just don't bind to 0.0.0.0; uvicorn picks 127.0.0.1 + an OS-
assigned free port, we poll /health until it's reachable, then a
native window opens on that URL.

Closing the window stops the server cleanly so the process exits
without zombies. `--no-window` is a headless mode that skips
pywebview (useful for tests, CI, or when you'd rather a normal
browser).

The frontend bundle must exist at `frontend/dist/index.html` before
launch — that's what the SPA catch-all in `backend/app/main.py`
hands out at `/`. Build it first with `make build`.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

log = logging.getLogger("openvinci.desktop")


def find_free_port(host: str = "127.0.0.1") -> int:
    """Ask the kernel for any free TCP port. Race-y in principle —
    another process could grab the port between this call and uvicorn
    binding — but in practice it's fine for a single-user launcher."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _ensure_backend_importable() -> None:
    """Make `backend/` importable so `from app.main import app` works
    without the user having to `pip install -e backend`."""
    backend_str = str(BACKEND_DIR)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)


def start_server(
    port: int, *, host: str = "127.0.0.1"
) -> tuple[Any, threading.Thread]:
    """Boot uvicorn against the FastAPI app in a daemon thread.

    Returns (server, thread). Call `stop_server(server, thread)` to
    shut it down.
    """
    import uvicorn  # imported here so tests of helpers below don't
                    # pay the cost when they aren't booting a server.

    _ensure_backend_importable()
    from app.main import app  # type: ignore[import-not-found]

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=os.environ.get("OPENVINCI_DESKTOP_LOG", "warning"),
        access_log=False,
        # No reload — desktop mode is one-shot; the file watcher
        # would otherwise spawn extra processes and confuse the
        # window close → exit handshake.
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        name="openvinci-desktop-server",
        daemon=True,
    )
    thread.start()
    return server, thread


def wait_for_health(
    port: int, *, host: str = "127.0.0.1", timeout: float = 10.0
) -> bool:
    """Poll /health until it returns 200 or `timeout` elapses.

    Polls every 50 ms — cheap because everything is local. Returns
    True iff the server is reachable. Quiet on failure; the caller
    decides how loud to be.
    """
    url = f"http://{host}:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:  # noqa: S310
                if r.status == 200:
                    return True
        except (
            urllib.error.URLError,
            ConnectionRefusedError,
            ConnectionResetError,
            OSError,
        ):
            pass
        time.sleep(0.05)
    return False


def stop_server(server: Any, thread: threading.Thread) -> None:
    """Tell uvicorn to exit and wait for the worker thread to die.

    Best-effort: uvicorn's `should_exit` is the documented shutdown
    hook; if a request is in flight it may take up to its keep-alive
    timeout to drop. We give it 5 seconds and move on either way.
    """
    server.should_exit = True
    thread.join(timeout=5.0)


def _open_window(
    url: str,
    *,
    title: str = "OpenVinci",
    width: int = 1280,
    height: int = 860,
    on_closing: Any | None = None,
) -> None:
    """Spawn the pywebview window. Blocks until every window closes.

    Importing pywebview here keeps the headless `--no-window` flow
    usable on systems where pywebview's GTK/QT backend isn't
    installable.
    """
    import webview  # type: ignore[import-not-found]

    window = webview.create_window(
        title,
        url,
        width=width,
        height=height,
        resizable=True,
    )
    if on_closing is not None and hasattr(window, "events"):
        # `events.closing` was added in pywebview 4.x; older versions
        # just exit when the window closes — fine for us, the
        # stop_server call after webview.start() returns covers both.
        with contextlib.suppress(Exception):
            window.events.closing += on_closing
    webview.start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m desktop.app",
        description=(
            "Launch OpenVinci as a desktop app: boots the FastAPI "
            "backend on 127.0.0.1 (free port) and opens a pywebview "
            "window against it."
        ),
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help=(
            "Skip pywebview; print the local URL and block until "
            "Ctrl+C. Useful for tests, CI, or when you'd rather use "
            "a normal browser."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Bind to this port instead of asking the kernel for one.",
    )
    parser.add_argument(
        "--health-timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for /health to come up (default 10).",
    )
    args = parser.parse_args(argv)

    # Sanity: the SPA catch-all expects frontend/dist/index.html.
    # Bail loudly if it's missing — no friendly 503 dance in desktop
    # mode where the user clearly meant to see the UI.
    index_html = FRONTEND_DIST / "index.html"
    if not index_html.is_file():
        print(
            f"frontend bundle missing at {index_html}\n"
            "  run `make build` (or `cd frontend && npm run build`) first.",
            file=sys.stderr,
        )
        return 2

    port = args.port if args.port > 0 else find_free_port()
    url = f"http://127.0.0.1:{port}"

    print(f"OpenVinci: starting server at {url} …", flush=True)
    server, thread = start_server(port)

    try:
        if not wait_for_health(port, timeout=args.health_timeout):
            print(
                f"OpenVinci: server did not respond at {url}/health within "
                f"{args.health_timeout:.0f}s — aborting.",
                file=sys.stderr,
            )
            return 1

        if args.no_window:
            print(
                f"OpenVinci: ready at {url} (open in a browser; "
                "press Ctrl+C to stop).",
                flush=True,
            )
            try:
                while thread.is_alive():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                print("OpenVinci: shutting down.", flush=True)
            return 0

        # Open the native window. webview.start() blocks until every
        # window closes; on close we tell uvicorn to exit. The
        # on_closing hook covers the case where webview tears down
        # before our cleanup code runs, so the server actually stops.
        def _on_closing() -> None:  # pragma: no cover — needs pywebview
            server.should_exit = True

        _open_window(url, on_closing=_on_closing)
        return 0
    finally:
        stop_server(server, thread)


if __name__ == "__main__":
    sys.exit(main())
