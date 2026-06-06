# OpenVinci — 5-minute demo

Goal: take a real CAN database, build a wired AUTOSAR COM-stack
project from it in one command, edit a signal, generate the C code,
and watch the four verification levels go green.

A scripted version of this whole walkthrough lives at
[`scripts/demo.sh`](../scripts/demo.sh). It runs headless and exits
0 on success — useful as a CI smoke beyond `verify.sh`. Read on for
the interactive version.

## 0. Prerequisites (one-time, ~30 s)

```sh
git submodule update --init     # vendor/as
make install                    # python venv + npm install
```

## 1. Import a DBC → a wired project (5 s)

```sh
backend/.venv/bin/openvinci-import-dbc \
    examples/dbc/sample.dbc \
    --out /tmp/openvinci-demo \
    --network CAN0 \
    --me AS
```

The sample DBC declares two messages (`STATUS` sent by `AS`,
`HEARTBEAT` sent by `Other`), each with a few signals. The
importer parses them with `cantools`, maps them onto Com IPDUs +
signals, and uses the engine's derivation functions to auto-wire:

- a Can controller for `CAN0`,
- CanIf Rx/Tx PDUs (`CAN0_STATUS_TX`, `CAN0_HEARTBEAT_RX` — the
  upstream `<Network>_<Message>_<TX|RX>` naming convention),
- PduR routines that connect Com ⇄ CanIf for each message.

You should see:

```
wrote 4 files to /tmp/openvinci-demo:
  config/Can/Can.json
  config/Com/Com.json
  config/Com/CanIf.json
  config/Com/PduR.json
```

That project is already valid + generate-ready. Confirm:

```sh
PYTHONPATH= backend/.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, "backend")
from engine import load_project, validate
report = validate(load_project("/tmp/openvinci-demo"))
print(f"ok={report.ok}  errors={len(report.errors)}  warnings={len(report.warnings)}")
PY
```

Output: `ok=True  errors=0  warnings=0`.

## 2. Edit a signal (10 s)

The imported project is plain JSON. The `Speed` signal on `STATUS`
came in with a `factor` of `0.1`. Change it to `0.05` — let's say
we're targeting a different unit:

```sh
python3 -c "
import json
p = '/tmp/openvinci-demo/config/Com/Com.json'
d = json.load(open(p))
sig = d['networks'][0]['messages'][0]['signals'][1]
print('was:', sig['name'], 'factor=', sig.get('factor'))
sig['factor'] = 0.05
json.dump(d, open(p, 'w'), indent=2)
print('now: factor=', sig['factor'])
"
```

The UI does the same thing — schema-driven typed editor, but for
the demo a one-line `jq`-equivalent makes the point.

(Alternatively: `make dev`, open <http://localhost:5173>, pick
`STATUS / Speed` in the tree, change `factor` in the form. Same
result; the backend persists nothing — that's the user's choice via
"save".)

## 3. Generate + compile (3 s)

```sh
PYTHONPATH= backend/.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, "backend")
from pathlib import Path
import tempfile
from engine import load_project
from gen import generate_and_compile
project = load_project("/tmp/openvinci-demo")
with tempfile.TemporaryDirectory() as tmp:
    result = generate_and_compile(project, Path(tmp))
    print(f"compile.status = {result.compile_result.status}")
    print(f"files:")
    for f in result.files:
        if f.path.endswith(('.c', '.h')):
            print(f"  {f.path:<40} module={f.module:<6} size={f.size_bytes}")
PY
```

Expected:

```
compile.status = ok
files:
  config/Com/GEN/CanIf_Cfg.c               module=CanIf  size=1887
  config/Com/GEN/CanIf_Cfg.h               module=CanIf  size=1688
  config/Com/GEN/Com_Cfg.c                 module=Com    size=...
  config/Com/GEN/Com_Cfg.h                 module=Com    size=...
  config/Com/GEN/PduR_Cfg.c                module=PduR   size=2432
  config/Com/GEN/PduR_Cfg.h                module=PduR   size=998
```

(Equivalent over HTTP, while `make dev` is running:)

```sh
curl -s -X POST http://localhost:8000/api/generate \
  -H 'content-type: application/json' \
  -d '{"project": '"$(jq -s '. as $a | {Can:$a[0], Com:$a[1], CanIf:$a[2], PduR:$a[3]}' \
        /tmp/openvinci-demo/config/Can/Can.json \
        /tmp/openvinci-demo/config/Com/Com.json \
        /tmp/openvinci-demo/config/Com/CanIf.json \
        /tmp/openvinci-demo/config/Com/PduR.json)"'}' \
  | jq '.compileResult.status, (.files | length)'
```

→ `"ok"`, `8`.

## 4. Green Verification Report (5 s)

```sh
make verify
```

Output:

```
==========================================
OpenVinci Verification Report
==========================================
  [PASS] L1 validate                    2s
  [PASS] L1 generate+compile            1s
  [PASS] L2 functional loopback         3s
  [PASS] L3 golden snapshot             1s
  [PASS] frontend (vitest)              2s
------------------------------------------
  RESULT: PASS
==========================================
```

That's the four levels described in [`README.md`](../README.md)
"How generated files are verified", green end-to-end against the
project we just imported, edited, and generated from.

## What this proved

- A real CAN database ingests cleanly into the OpenVinci model.
- The auto-wire produces a project that the engine validates with
  zero errors.
- An interactive edit (factor change) survives generation — the new
  value lands in the generated C, the C still parses against the BSW
  headers.
- The byte content of the generated files matches our golden
  snapshot (modulo timestamps); the simulator broker transports
  frames byte-exact at runtime.

## What this did NOT prove

Re-read the "What these levels do NOT claim" section of the README
before betting an ECU on it. tl;dr: not production-, hardware-, or
safety-certified.
