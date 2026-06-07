# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — bundle the desktop launcher + everything the
# backend reads at runtime into one double-click artifact.

from PyInstaller.utils.hooks import collect_submodules
#
# Run via `make desktop-app`. The build is intentionally per-OS:
# - Linux  → ELF binary at dist/OpenVinci
# - macOS  → .app under dist/
# - Win    → .exe under dist\
#
# What's bundled and why:
#
#   frontend/dist        the built SPA — served by the FastAPI catch-all
#                        when the user opens http://127.0.0.1:<port>/.
#   model                the Layer-1 JSON Schemas the UI fetches at
#                        boot via /schemas.
#   examples             bundled projects + the DBC drag/drop targets;
#                        the UI lists them via /api/projects.
#   vendor/as/tools      the upstream Python generators (Com.py,
#                        CanIf.py, PduR.py, CanTp.py, …). Bundled as
#                        raw .py files so `import generator` works
#                        after backend/gen/generate.py mutates
#                        sys.path at runtime.
#   vendor/as/infras     header tree the optional gcc -fsyntax-only
#                        verification step uses. Generation works
#                        WITHOUT this dir; only compile_check needs it,
#                        and only when gcc is on PATH (see
#                        backend/gen/compile.py's "unavailable" status).
#
# The desktop launcher (`desktop/app.py`) sets OPENVINCI_FRONTEND_DIST,
# OPENVINCI_EXAMPLES_DIR, OPENVINCI_SCHEMAS_DIR and OPENVINCI_VENDOR_AS
# from `sys._MEIPASS` BEFORE importing the backend, so the rest of the
# code stays bundle-mode-agnostic.

from pathlib import Path

# SPECPATH is set by PyInstaller when it runs this file.
ROOT = Path(SPECPATH).resolve()


def under(rel: str) -> str:
    return str(ROOT / rel)


block_cipher = None

a = Analysis(
    [under("desktop/app.py")],
    # `pathex` is search path for Analysis; the backend package lives
    # under backend/ so PyInstaller can find `app`, `engine`, `gen`,
    # `importer` via static `import` walks.
    pathex=[under("backend")],
    binaries=[],
    datas=[
        (under("frontend/dist"),    "frontend/dist"),
        (under("model"),            "model"),
        (under("examples"),         "examples"),
        (under("vendor/as/tools"),  "vendor/as/tools"),
        (under("vendor/as/infras"), "vendor/as/infras"),
        # License + README — keep beside vendor/as so the bundle is
        # compliant out of the box without a chase to find them.
        (under("vendor/as/LICENSE"),   "vendor/as"),
        (under("vendor/as/README.md"), "vendor/as"),
        (under("README.md"),        "."),
        # The H7 firmware-export template (driver / board / linker /
        # Makefile + a trimmed CMSIS subset). project_export.py reads
        # from gen/h7_template/ at runtime — bundle it so the desktop
        # app can produce H7 exports without the embedded-firmware
        # tree being on disk.
        (under("backend/gen/h7_template"), "gen/h7_template"),
    ],
    hiddenimports=[
        # Backend modules — the FastAPI app entrypoint and its sibs.
        # PyInstaller usually catches these via the import walk but
        # listing them defensively keeps the bundle stable across
        # future analyzer changes.
        "app.main",
        "app.model",
        "engine",
        "gen",
        "importer",
        # uvicorn loads its protocol/worker classes by string at boot.
        "uvicorn.loops.auto",
        "uvicorn.lifespan.on",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        # vendor/as/tools/generator imports these at module load. The
        # generator tree is shipped as DATA files (so `import generator`
        # finds them via the sys.path mutation in
        # backend/gen/generate.py), but the analyzer never crawled
        # them — list their third-party deps here so the bundle still
        # has them on the python frozen archive.
        "pycrc.algorithms",
        "ply",
        "ply.lex",
        "ply.yacc",
        "jinja2",
        "bitarray",
        # vendor/as/tools/generator/__init__.py imports `from .Rte
        # import Gen as RteGen` unconditionally, and Rte.py does
        # `from building import *` which transitively imports SCons +
        # SCons.Script. We don't drive Rte / asar generators in the
        # UI, but the side-effect import must resolve cleanly or the
        # whole `import generator` fails.
        # SCons dynamically loads platform/tool modules by name at
        # IMPORT TIME of `building.py` (vendor/as/tools/building.py:
        # `from SCons.Script import *` triggers DefaultEnvironment()
        # which needs SCons.Platform.posix AND SCons.Tool.default
        # AND every Tool the default chain references). Easier to
        # collect every SCons submodule than to chase them one by
        # one — adds ~5 MB to the bundle but stays robust across
        # SCons versions.
        *collect_submodules("SCons"),
        # `autosar` is only needed by a few generators we don't drive
        # from /api/generate (RTE / asar). The static analyzer pulls
        # in its core anyway; we don't list submodules to keep bundle
        # size sane.
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Pulled in transitively by some deps; we don't render Tk.
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="OpenVinci",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Console attaches a terminal on Windows for `--no-window` debug
    # use; leave it on by default so the bundle is usable from a
    # command-line shell. Flip to False for a console-less GUI build.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
