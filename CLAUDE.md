# CLAUDE.md — OpenVinci

OpenVinci is an open-source, developer-focused configurator for the
AUTOSAR Classic COM stack. It builds on `autoas/as`
(https://github.com/autoas/as) which is vendored as a git submodule
at `vendor/as/`.

Before doing anything in this repo, read these two — they are the
contract:

- `docs/AUTOAS_NOTES.md` — exactly what `vendor/as` accepts, exposes,
  and builds. Every claim is cited to a file in the submodule.
- `docs/ARCHITECTURE.md` — the four layers (schema model, validation
  engine, generation adapter, React UI) and how they fit together.

## Repository layout

```
OpenVinci/
├── CLAUDE.md              # this file
├── docs/
│   ├── AUTOAS_NOTES.md
│   └── ARCHITECTURE.md
├── schemas/               # Layer 1: JSON Schemas (not yet authored)
├── openvinci/             # Layer 2 + 3: Python package (not yet authored)
│   ├── engine/            #   - Layer 2 (validation + derivation)
│   └── adapter/           #   - Layer 3 (HTTP wrapper around vendor/as)
├── web/                   # Layer 4: React + TS app (not yet authored)
└── vendor/
    └── as/                # autoas/as as a git submodule
```

Layers 1–4 are described in `docs/ARCHITECTURE.md`. Right now this repo
only contains the recon docs and the submodule; the rest is the work
ahead.

## Conventions

### Submodule discipline
- **Never patch `vendor/as` from this repo.** It is a vendored upstream
  read-only dependency. If we need a change there, file/upstream a PR
  against `autoas/as` and bump the submodule SHA.
- After pulling, always run `git submodule update --init --recursive`.
- When the submodule SHA moves, re-check the generator Python in
  `vendor/as/tools/generator/` for schema drift before merging — see
  the "schema drift" note in `docs/ARCHITECTURE.md`.

### Config files (the JSON the COM stack uses)
- Live under a "project" directory laid out the way `vendor/as`
  already expects (`<proj>/config/<Module>/<Module>.json`). Do not
  invent a new on-disk shape — see `docs/ARCHITECTURE.md` §3.3.
- Every config has a top-level `"class"` matching one of the keys in
  `vendor/as/tools/generator/__init__.py:__GEN__`. Add a new class only
  after the matching generator exists upstream.

### Python (Layers 2 + 3)
- Python 3.10+ (matches what `vendor/as`'s SCons + PyQt5 already need).
- Format with `black` (the submodule already ships a `.black` config
  at `vendor/as/.black` — match it for any Python that touches the
  generators).
- Lint with `ruff`. No `mypy` requirement yet; revisit when the engine
  package crosses ~2 kLoC.
- Public API of `openvinci.engine` is documented in
  `docs/ARCHITECTURE.md` §2.4 — keep it stable; everything else is
  internal.

### Web (Layer 4)
- TypeScript strict mode; no `any`.
- Prettier defaults; ESLint with the standard React + TS recipe.
- The UI must fetch schemas at runtime from the adapter
  (`GET /schemas`). Do not bundle schemas into the JS.

### General
- Don't add comments that just restate what the code does. Comments
  explain WHY (a non-obvious constraint, a workaround for an upstream
  quirk). Cite `vendor/as/...:LINE` when the reason lives upstream.
- Avoid new dependencies. Anything we add here needs a one-line
  justification in the PR description.
- When in doubt, write the test first against an example config under
  `vendor/as/app/app/config/` — those are the ground truth.

## Build and test commands

The OpenVinci layers are not built yet. Until they are, the commands
below refer to the `vendor/as` build chain (which OpenVinci wraps).

### Prerequisites
```sh
git submodule update --init --recursive
python -m pip install scons pyserial pybind11 pillow ply pyqt5 bitarray
# Windows-only: see vendor/as/doc/EN/build-env-setup.md for MSYS2 setup.
```

### Generate C code from a project's JSON (no build)
```sh
# Standalone, no SCons:
python - <<'PY'
import sys; sys.path.append("vendor/as/tools")
from generator import Generate
Generate([
    "vendor/as/app/app/config/Com/Com.json",
    "vendor/as/app/app/config/Com/CanIf.json",
    "vendor/as/app/app/config/Com/PduR.json",
    "vendor/as/app/app/config/CanTp/CanTp.json",
], True)
PY
# Outputs land in <Module>/GEN/ next to each JSON.
```

### Build the host-sim demo apps
```sh
cd vendor/as
scons --app=CanSimulator        # CAN broker over IP socket
scons --app=CanApp              # full COM stack (Com/CanIf/CanTp/PduR/...)
scons --app=IsoTpSend           # diagnostic tester
scons --lib=AsPy                # Python bindings (used by asone, tests)
scons --gen --app=CanApp        # force-regenerate before building
```
Binaries land in `vendor/as/build/<os>/GCC/<AppName>/<AppName>{.exe}`
(Windows uses `build/nt/...`, Linux uses `build/posix/...` per
`vendor/as/tools/building.py:51-60`).

### Run the host simulation
```sh
# Terminal 1: CAN bus broker on bus 0
vendor/as/build/posix/GCC/CanSimulator/CanSimulator 0
# Terminal 2: COM-stack node
vendor/as/build/posix/GCC/CanApp/CanApp
# Terminal 3 (optional): UDS tester
vendor/as/build/posix/GCC/IsoTpSend/IsoTpSend -v 1001
```

### Launch the upstream PyQt5 JSON editor (parity baseline)
```sh
cd vendor/as/tools/json.editor
python main.py                                  # default schema
python main.py -c ../../app/app/config/Com/Com.json
```

### Launch asone (the upstream Qt GUI we'll be replacing)
```sh
cd vendor/as/tools/asone
python main.py        # Python edition; auto-builds AsPy on first run
# C++ edition: scons --lib=AsOne, then asone binary
```

### Tests (placeholders — to be added with each layer)
```sh
# Layer 1 (schemas): every example under vendor/as/app/app/config must validate
pytest tests/schemas/

# Layer 2 (engine):
pytest openvinci/engine/

# Layer 3 (adapter):
pytest openvinci/adapter/

# Layer 4 (web):
cd web && npm test && npx playwright test
```

## Things that will trip you up

- `vendor/as` uses dual licensing (GPLv3 + commercial) — OpenVinci
  treats it as a runtime dependency, not as code we redistribute.
- The generator factory key is `"class"` in each JSON. There is **no**
  `class: "Can"` generator — the low-level CAN driver config is a hand
  written C file (`docs/AUTOAS_NOTES.md` §1.2).
- The GUI schema at `vendor/as/tools/json.editor/schema.json` is not a
  conformant JSON Schema (custom `enumref`, `enabled`, `friends`). Don't
  treat it as authoritative — the generator Python is.
- `scons` writes a `.gendb.pkl` cache at the submodule root that skips
  regeneration if `(json, dbc, ldf)` hashes are unchanged. Use `--gen`
  to bypass it (`tools/generator/__init__.py:124-150`).
- Build artefact path differs by OS: `build/nt/...` on Windows,
  `build/posix/...` on Linux (`tools/building.py:51-60`).
