"""Desktop launcher for OpenVinci.

`python -m desktop.app` boots the same FastAPI app the hosted flow
runs (`backend/app/main.py`), points uvicorn at 127.0.0.1 on an
OS-assigned free port, and opens a native pywebview window against
that URL. See `desktop/app.py` for the entry point and `README.md`
under "Run as a desktop app" for prerequisites + install.
"""
