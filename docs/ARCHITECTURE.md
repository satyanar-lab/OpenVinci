# OpenVinci — Architecture

OpenVinci is an open-source, developer-focused configurator for the
AUTOSAR Classic COM stack, modeled on Vector DaVinci Configurator and
built on top of `autoas/as` (in this repo as the `vendor/as` submodule).

The non-negotiable design decision: **`vendor/as` is the only source of
truth for generated C code**. OpenVinci wraps it; it does not fork it.
The configs OpenVinci produces are the same JSON files `vendor/as` already
consumes (`docs/AUTOAS_NOTES.md` §1). Everything else is layered on top.

```
            ┌──────────────────────────────────────────────────┐
   user →   │  Layer 4: React Web UI (browser)                 │  TypeScript
            │  - schema-driven forms, validation chrome, diff  │
            └────────────────────┬─────────────────────────────┘
                                 │ HTTP / JSON
            ┌────────────────────▼─────────────────────────────┐
            │  Layer 3: Generation Adapter (Python service)    │  Python
            │  - wraps tools/generator.Generate                │
            │  - subprocess `scons --app=...` on demand        │
            └────────────────────┬─────────────────────────────┘
                                 │ in-proc
            ┌────────────────────▼─────────────────────────────┐
            │  Layer 2: Validation + Derivation Engine         │  Python
            │  - JSON Schema validate + cross-file rules       │
            │  - DBC import → Com.messages / CanIf.{Rx,Tx}Pdus │
            └────────────────────┬─────────────────────────────┘
                                 │ load/save
            ┌────────────────────▼─────────────────────────────┐
            │  Layer 1: Model (JSON Schema over vendor/as JSON)│  JSON Schema
            │  - Draft 2020-12 schemas for Can/CanIf/CanTp/    │
            │    PduR/Com that match what generator.Generate   │
            │    expects, with cross-file $refs                │
            └──────────────────────────────────────────────────┘
                                 ▲
                                 │ ground truth
            ┌────────────────────┴─────────────────────────────┐
            │  vendor/as  (git submodule)                      │
            │  generator.Generate, building.py, simulator/, …  │
            └──────────────────────────────────────────────────┘
```

A useful one-liner: **Layer 1 says what's legal, Layer 2 says it's
internally consistent, Layer 3 turns it into C, Layer 4 lets a human
edit it.**

---

## Layer 1 — Model: JSON Schema over the autoas/as config format

**Purpose.** Give the rest of the system a single, machine-readable
description of every field `vendor/as` accepts, so the UI, validator, and
adapter all agree on shape.

**Why a schema, not Python classes.** `vendor/as` already keeps the data
in JSON (`docs/AUTOAS_NOTES.md` §1.1). A JSON Schema lets us:

- drive UI forms automatically (the React side uses `react-jsonschema-form`
  or an equivalent — see Layer 4),
- validate before invoking generators (cheap, no scons needed),
- diff and version configs as data.

**Layout.** One schema per `class` value the generator factory recognises
(`vendor/as/tools/generator/__init__.py:44-76`). For the COM stack:

```
schemas/
  com.schema.json        # class:"Com"
  canif.schema.json      # class:"CanIf"
  cantp.schema.json      # class:"CanTp"
  pdur.schema.json       # class:"PduR"
  can.schema.json        # *not* in vendor/as __GEN__ — OpenVinci-only
                         #   metadata around the hand-written Can_Cfg.c
                         #   (see docs/AUTOAS_NOTES.md §1.2 "Can")
  shared/
    types.schema.json    # PduRef, NetworkRef, hex integer, etc.
    refs.schema.json     # $defs for cross-file references
```

**How we author them.** Each schema is hand-derived from three sources,
in this priority order, and every property carries a comment pointing back
to its origin:

1. The generator Python — this is the actual contract
   (`tools/generator/CanIf.py`, `Com.py`, etc.).
2. The GUI schema at `vendor/as/tools/json.editor/schema.json` — for
   defaults, ranges, enums, conditional visibility.
3. The doc-comments in `vendor/as/doc/EN/{Com,CanIf,CanTp,PduR}.md`.

**What's *not* in Layer 1.** Cross-file relationships (CanTp channel `X`
needs CanIf `X_RX`/`X_TX`, PduR routine `name` must exist in CanIf, etc.)
live in Layer 2 — JSON Schema can't express them cleanly. Layer 1 limits
itself to single-document shape and type rules. Conditional visibility (the
GUI's `"enabled": "'${use_dbc}' == 'True'"`) is translated into JSON
Schema `if/then/else`.

**Versioning.** The schema files carry `"$id": "https://openvinci.dev/
schema/<module>/v1.json"` and a `vendoredAsCommit` field naming the
`vendor/as` SHA they were derived from. When the submodule moves, a CI
job re-runs a `tools/check_schema_drift.py` that walks the generator
Python and flags new/changed keys.

---

## Layer 2 — Headless validation + derivation engine

A Python package (`openvinci/engine/`) with no GUI, no HTTP — pure
functions over the model. It is the only place schema rules and
cross-file rules live.

### 2.1 Responsibilities

| Capability               | Inputs                                | Output                                                            |
|--------------------------|---------------------------------------|-------------------------------------------------------------------|
| Schema validation        | One JSON file + its schema            | Pass/fail + structured error list (path, message, expected)       |
| Cross-file validation    | A project (set of JSON files)         | Pass/fail + structured error list                                 |
| DBC import (derivation)  | A `.dbc` path + a target network name | A patch describing `Com.messages` and `CanIf.{Rx,Tx}Pdus` to add  |
| Default population       | A partial JSON + its schema           | A complete JSON with schema defaults filled in                    |
| Normalisation            | Any JSON                              | Canonical key order, hex format, line endings — for stable diffs  |

### 2.2 Cross-file rules (concrete, derived from `docs/AUTOAS_NOTES.md` §1.3)

```python
# openvinci/engine/rules.py — pseudocode
def check_cantp_canif(cantp, canif) -> Iterable[Issue]:
    canif_names = {p["name"] for n in canif["networks"]
                             for p in n["RxPdus"] + n["TxPdus"]}
    for ch in cantp["channels"]:
        for suffix in ("_RX", "_TX"):
            if ch["name"] + suffix not in canif_names:
                yield Issue(
                    path=f"CanTp.channels[{ch['name']}]",
                    message=f"missing CanIf PDU {ch['name']}{suffix}",
                    fix_hint=f"add to CanIf.networks[*].{ 'Rx' if suffix=='_RX' else 'Tx' }Pdus",
                )
```

Each rule is a small generator yielding `Issue` records. New rules go
beside it; there is no central rule registry beyond a `RULES = [...]`
list — adding a rule is one PR, not three.

The rule set the COM stack needs on day one:

1. CanIf PDU `name` is globally unique (`docs/AUTOAS_NOTES.md` §1.3).
2. CanTp channel `X` ⇒ CanIf `X_RX` + `X_TX` exist with `up: "CanTp"`.
3. PduR routine `name` exists as a CanIf PDU **or** a Com PDU/signal.
4. PduR `from`/`to` only references modules actually configured.
5. CanIf `up` values reference only modules present in the project (or
   `User*` per the upstream callback convention).
6. Com `messages[*].id` doesn't collide with a DBC-derived ID on the
   same network.
7. DBC referenced by Com/CanIf/PduR exists and parses.
8. CanIf network `name` set = PduR network `name` set = Com network
   `name` set.

### 2.3 DBC import / derivation

`vendor/as/tools/generator/dbc/` already has a DBC parser, and
`tools/json.editor/plugin/ImportDBC.py:9` already does
`from generator.dbc import dbc`. The engine reuses that parser instead
of pulling a second one. The derivation produces a patch (RFC 6902 JSON
Patch) rather than mutating in place, so the UI can preview before
applying.

### 2.4 Public Python API

```python
from openvinci.engine import Project

p = Project.load("./my-ecu/")        # discovers *.json by "class" key
p.validate()                          # → ValidationReport
p.import_dbc("Com", "CAN0", "CAN0.dbc")   # → JsonPatch (not applied yet)
p.apply(patch)
p.save()
```

Everything in this layer is synchronous, side-effect-free except for
explicit `save()` / `apply()`, and trivially unit-testable. Layer 3 wraps
it in HTTP; Layer 4 talks to Layer 3, never to Layer 2 directly.

---

## Layer 3 — Generation Adapter

A thin Python service (FastAPI or stdlib `http.server` — sized to the
need, not the fashion) that wraps `vendor/as`'s generators and build.

### 3.1 What it wraps

Two upstream entry points, both verified in `docs/AUTOAS_NOTES.md` §2:

```python
# 3a: generate C code from JSON (no build)
import sys; sys.path.append("vendor/as/tools")
from generator import Generate
Generate([".../Com.json", ".../CanIf.json", ...], force=True)
# writes GEN/*.h, GEN/*.c next to each JSON

# 3b: build a host-sim app (optional, for "Run" button)
subprocess.run(["scons", "--app=CanApp"], cwd="vendor/as", check=True)
```

### 3.2 HTTP surface (minimal, JSON in / JSON out)

| Method | Path                          | Purpose                                          |
|--------|-------------------------------|--------------------------------------------------|
| GET    | `/projects/{p}`               | Tree of files + parsed JSON                      |
| PUT    | `/projects/{p}/files/{name}`  | Save a single module JSON                        |
| POST   | `/projects/{p}/validate`      | Run Layer 2; return issues                       |
| POST   | `/projects/{p}/import-dbc`    | Body: `{module, network, dbcPath}` → JSON Patch  |
| POST   | `/projects/{p}/generate`      | Run upstream generators; return file list + diff |
| POST   | `/projects/{p}/build`         | Run `scons --app=...`; stream stdout via SSE     |
| GET    | `/schemas`                    | Bundle all Layer-1 schemas (for the UI)          |

The adapter does no business logic — every call delegates to Layer 2 or
to `vendor/as`. That separation is the point: when `vendor/as` ships a
new generator or breaks a contract, only this layer changes.

### 3.3 Where files live at runtime

A "project" is a directory laid out the way `vendor/as` already expects
(`app/app/config/<Module>/<Module>.json`). The adapter does not invent a
new on-disk shape — that lets the user drop an OpenVinci project into a
checkout of `autoas/as` and have it build, unmodified.

### 3.4 Process model

`Generate()` is in-process Python; cheap (sub-second on a full CanApp
project). `scons` is `subprocess.run`. Build output is streamed back via
Server-Sent Events; no WebSocket framework. Concurrent builds in one
project are serialised by a per-project lockfile.

---

## Layer 4 — React Web UI

A single-page React + TypeScript app served either by the adapter (for
local dev) or as static files behind any web server (for hosted use).

### 4.1 Stack choices and why

| Choice                        | Why                                                                                |
|-------------------------------|------------------------------------------------------------------------------------|
| React + Vite + TypeScript     | Fast feedback loop; types catch most of the wire-format errors at the boundary.    |
| `@rjsf/core` (`react-jsonschema-form`) | Reuses the Layer-1 schemas directly. Custom widgets only for hex inputs, PDU pickers, signal layout. |
| Zustand (small global store)  | Avoids the Redux boilerplate; project state is small (megabytes of JSON, not GB).  |
| TanStack Query                | Caches `/schemas` and `/projects/{p}` cleanly; surfaces errors uniformly.          |
| Monaco                        | The "raw JSON" view; the same editor power-users already know.                     |

No CSS framework picked yet — keep it plain CSS modules until the design
needs more. (Picking Tailwind or shadcn before there are five screens is
the kind of premature-abstraction this README is supposed to push back on.)

### 4.2 Screens

1. **Project browser** — list of projects, "New from template" (CanApp,
   minimal-Com-only), "Open existing directory".
2. **Module editor (per-class)** — form generated from the schema,
   plus a Monaco "raw JSON" toggle. Validation issues from Layer 2 render
   inline next to the offending field.
3. **DBC import wizard** — pick a DBC, preview the patch, accept/decline
   per message.
4. **Project validate** — full report, grouped by module, click-to-jump.
5. **Generate & build** — runs Layer 3 endpoints; shows generated file
   tree and a streaming build log.
6. **Diff view** — before/after JSON for any unsaved change.

### 4.3 What the UI does *not* do

- Talk to `vendor/as` directly. (Goes through Layer 3.)
- Implement validation rules. (Layer 2 owns those; the UI just renders
  the `Issue` list.)
- Know schemas at build time. (Fetches them from `/schemas` so a schema
  edit doesn't require rebuilding the UI.)

---

## Cross-cutting concerns

### Configuration / project storage

A project is a directory on disk. No database. The adapter watches the
directory with `watchdog` for external edits and pushes refresh events
to the UI over SSE. This keeps `vendor/as`-native tooling (CLI scons
builds, the upstream PyQt5 editor) interoperable: any of them can edit
the JSON, OpenVinci just notices.

### Submodule discipline

Everything OpenVinci-specific (schemas, engine, adapter, web UI) lives
*outside* `vendor/as`. We do not patch the submodule. If upstream is
missing something we need (e.g. a programmatic "list registered apps"
hook), we either work around it in Layer 3 (parse `tools/building.py`
output) or upstream a PR.

### Testing strategy

- Layer 1: schema unit tests with `jsonschema` library — every example
  config under `vendor/as/app/app/config/` must validate cleanly.
- Layer 2: pytest, including a golden-file test that runs every cross-file
  rule against `vendor/as/app/app/config/Com/*` and `CanTp/*` and asserts
  zero issues.
- Layer 3: pytest + `httpx` against the adapter; `Generate` is mocked in
  fast tests, exercised for real in a slow integration test that does a
  full `scons --app=CanApp` and asserts the binary runs.
- Layer 4: Playwright on the golden-path screens (new project → edit
  message → validate → generate → build).

### Failure modes we explicitly design for

- **Upstream generator throws.** Layer 3 captures stderr, returns it
  unchanged. The UI shows the trace verbatim — do not pretty-print, the
  line numbers are the value.
- **Schema drift vs vendor/as.** CI compares the current schema set to a
  walk of the generator Python; a mismatch fails the build with a diff
  pointing at the new/removed keys.
- **Two clients editing one file.** Last-write-wins on the file; the UI
  warns when its in-memory mtime is older than the disk's.

### Non-goals (for now)

- Arxml import/export. (Possible later via the same adapter pattern.)
- Multi-ECU system view. `vendor/as` is one-ECU-at-a-time; OpenVinci
  inherits that.
- Replacing scons. The build system is `vendor/as`'s, full stop.
