#!/usr/bin/env bash
# OpenVinci headless demo — runs the docs/DEMO.md walkthrough end to end.
#
#   import sample DBC → edit a signal → generate+compile → verify
#
# Exits 0 on success, non-zero on any step failure. Intended for both
# human eyes (clear section headers + check marks) and CI smoke beyond
# scripts/verify.sh.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/backend/.venv"
IMPORT_DBC="$VENV/bin/openvinci-import-dbc"
PY="$VENV/bin/python"

if [ ! -x "$PY" ] || [ ! -x "$IMPORT_DBC" ]; then
    echo "demo: backend venv not installed — run 'make install' first" >&2
    exit 2
fi

export PYTHONPATH=""
export PYTHONNOUSERSITE="1"

PROJECT_DIR="${OPENVINCI_DEMO_DIR:-$(mktemp -d --suffix=-openvinci-demo)}"
SAMPLE_DBC="$ROOT/examples/dbc/sample.dbc"

section() {
    echo
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

check() {
    echo "  ✓ $1"
}

cleanup() {
    if [ -z "${OPENVINCI_DEMO_DIR:-}" ] && [ -d "$PROJECT_DIR" ]; then
        rm -rf "$PROJECT_DIR"
    fi
}
trap cleanup EXIT

# ---- 1. import DBC --------------------------------------------------
section "Step 1 — import sample DBC into a fresh project"

"$IMPORT_DBC" "$SAMPLE_DBC" \
    --out "$PROJECT_DIR" \
    --network CAN0 \
    --me AS \
    --force \
    | sed 's/^/  /'

for f in config/Can/Can.json config/Com/Com.json \
         config/Com/CanIf.json config/Com/PduR.json; do
    if [ ! -s "$PROJECT_DIR/$f" ]; then
        echo "demo: expected $f to exist" >&2
        exit 3
    fi
done
check "imported sample.dbc → 4 JSON files"

# ---- 2. validate the imported project --------------------------------
section "Step 2 — validate the imported project"

"$PY" - "$PROJECT_DIR" <<'PY'
import sys
sys.path.insert(0, "backend")
from engine import load_project, validate

project_dir = sys.argv[1]
report = validate(load_project(project_dir))
print(f"  ok={report.ok}  errors={len(report.errors)}  warnings={len(report.warnings)}")
if not report.ok:
    for i in report.errors:
        print(f"  [error] {i.rule}: {i.message}")
    sys.exit(1)
PY

check "engine.validate → ok"

# ---- 3. edit a signal ------------------------------------------------
section "Step 3 — edit the Speed signal's factor (0.1 → 0.05)"

"$PY" - "$PROJECT_DIR" <<'PY'
import json, sys
project_dir = sys.argv[1]
path = f"{project_dir}/config/Com/Com.json"
data = json.load(open(path))
network = data["networks"][0]
status_msg = next(m for m in network["messages"] if m["name"] == "STATUS")
speed_sig = next(s for s in status_msg["signals"] if s["name"] == "Speed")
old = speed_sig.get("factor")
speed_sig["factor"] = 0.05
with open(path, "w") as f:
    json.dump(data, f, indent=2)
print(f"  was: factor={old}")
print(f"  now: factor={speed_sig['factor']}")
PY

check "Speed.factor updated in Com.json"

# ---- 4. validate again ----------------------------------------------
section "Step 4 — re-validate (edit must not break anything)"

"$PY" - "$PROJECT_DIR" <<'PY'
import sys
sys.path.insert(0, "backend")
from engine import load_project, validate

report = validate(load_project(sys.argv[1]))
print(f"  ok={report.ok}  errors={len(report.errors)}  warnings={len(report.warnings)}")
sys.exit(0 if report.ok else 1)
PY

check "still valid"

# ---- 5. generate + compile ------------------------------------------
section "Step 5 — generate + compile (VERIFICATION LEVEL 1)"

"$PY" - "$PROJECT_DIR" <<'PY'
import sys, tempfile
sys.path.insert(0, "backend")
from pathlib import Path
from engine import load_project
from gen import generate_and_compile

project_dir = sys.argv[1]
project = load_project(project_dir)
with tempfile.TemporaryDirectory() as tmp:
    result = generate_and_compile(project, Path(tmp))
    cr = result.compile_result
    print(f"  compile.status = {cr.status}")
    cfiles = sum(1 for f in result.files if f.path.endswith('.c'))
    hfiles = sum(1 for f in result.files if f.path.endswith('.h'))
    print(f"  generated      = {len(result.files)} files ({cfiles}.c, {hfiles}.h)")
    if cr.status != "ok":
        for m in cr.messages:
            if m.severity == "error":
                print(f"  [{m.severity}] {m.file}:{m.line} {m.message}")
        sys.exit(1)
PY

check "L1: every generated *_Cfg.c compiles against vendor/as BSW headers"

# ---- 6. golden snapshot (silently — would fail loudly if drift) -----
section "Step 6 — golden snapshot regression on com-minimal"

"$VENV/bin/pytest" "$ROOT/tests/golden" -q \
    > "${PROJECT_DIR}/golden.log" 2>&1 && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
    echo "demo: golden snapshot drifted:"
    cat "${PROJECT_DIR}/golden.log"
    exit 4
fi
check "L3 golden snapshot matches"

# ---- 7. final report ------------------------------------------------
section "✅  Demo complete"

echo "  Imported a DBC, edited a signal, generated + compiled the result,"
echo "  and verified byte-stability against the L3 snapshot."
echo
echo "  Run 'make verify' for the full 4-level Verification Report."
echo "  The project lives at: $PROJECT_DIR"
if [ -z "${OPENVINCI_DEMO_DIR:-}" ]; then
    echo "  (cleaned up on exit — set OPENVINCI_DEMO_DIR=<path> to keep it)"
fi
