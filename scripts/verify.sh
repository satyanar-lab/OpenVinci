#!/usr/bin/env bash
# OpenVinci verification — run every level in order, print a single report.
#
# Levels:
#   1. validate           — model + engine unit tests (round-trip, schema,
#                           validation rules, derive, solve)
#   2. generate+compile   — gen pipeline: stage → vendor/as generators →
#                           gcc -c -fsyntax-only against BSW headers
#   3. functional loopback — vendor/as can_simulator broker, raw socket
#                           frame transport with byte-exact fidelity
#   4. golden             — regenerate, normalize timestamps, byte-diff
#                           against tests/golden/<example>/expected/
#
# Each level reports PASS/FAIL on its own line. Exit code = 0 iff all pass.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/backend/.venv"
PYTEST="$VENV/bin/pytest"
NPM="$(command -v npm || true)"

# Strip inherited PYTHONPATH so a system Python (ROS et al.) doesn't
# leak unrelated pytest plugins into our venv. Matches Makefile.
export PYTHONPATH=""
export PYTHONNOUSERSITE="1"

LOG_DIR="$ROOT/build/verify"
mkdir -p "$LOG_DIR"

# Compatible with `set -u`: avoid associative arrays so older bashes work.
LEVEL_NAMES=()
LEVEL_RESULTS=()
LEVEL_DURATIONS=()
LEVEL_LOGS=()
OVERALL_RC=0

run_level() {
    local name="$1"; shift
    local logfile="$1"; shift
    local label="${name// /_}"
    echo "==> ${name}"
    local start end rc
    start=$(date +%s)
    if "$@" > "$logfile" 2>&1; then
        rc=0
    else
        rc=$?
    fi
    end=$(date +%s)
    local dur=$((end - start))
    LEVEL_NAMES+=("$name")
    LEVEL_DURATIONS+=("$dur")
    LEVEL_LOGS+=("$logfile")
    if [ "$rc" -eq 0 ]; then
        LEVEL_RESULTS+=("PASS")
        echo "    PASS (${dur}s)"
    else
        LEVEL_RESULTS+=("FAIL")
        OVERALL_RC=1
        echo "    FAIL (${dur}s) — see ${logfile#$ROOT/}"
        # Surface the tail of the log so the user knows immediately
        # what broke, without having to open another file.
        echo "    --- last 20 lines ---"
        tail -n 20 "$logfile" | sed 's/^/    /'
    fi
}

require_binary() {
    if ! command -v "$1" > /dev/null 2>&1; then
        echo "missing required binary: $1" >&2
        return 1
    fi
}

require_binary "$PYTEST" || {
    echo "Backend venv is missing — run 'make install' first." >&2
    exit 2
}
require_binary gcc || exit 2
require_binary g++ || exit 2

# vendor/as is a hard dependency for every level beyond Layer 1's pure
# JSON-Schema unit tests. L1-gen runs the upstream generators; L2 builds
# the broker from vendor/as sources; L3 regenerates against vendor/as.
# Silent-skipping any of these is the worst possible UX — a "PASS"
# report would actually mean "we didn't check." Fail loud instead.
if [ ! -d "$ROOT/vendor/as/infras" ]; then
    cat >&2 <<'EOF'
ERROR: vendor/as submodule is not initialized.

  expected: vendor/as/infras/  (and the rest of the autoas/as tree)
  found:    (missing)

run:
    git submodule update --init --recursive

then re-run scripts/verify.sh.
EOF
    exit 2
fi

# ---- L1 validate -----------------------------------------------------
run_level "L1 validate" "$LOG_DIR/l1-validate.log" \
    "$PYTEST" "$ROOT/backend/tests/engine" \
    "$ROOT/backend/tests/test_roundtrip.py" \
    "$ROOT/backend/tests/test_schemas.py" \
    "$ROOT/backend/tests/test_schemas_validate_examples.py" \
    "$ROOT/backend/tests/test_importer_dbc.py"

# ---- L1 generate+compile --------------------------------------------
run_level "L1 generate+compile" "$LOG_DIR/l1-gen-compile.log" \
    "$PYTEST" "$ROOT/backend/tests/test_gen_pipeline.py" \
    "$ROOT/backend/tests/test_gen_stage.py" \
    "$ROOT/backend/tests/test_api_generate.py"

# ---- L2 functional loopback -----------------------------------------
OPENVINCI_RUN_FUNCTIONAL=1 \
    run_level "L2 functional loopback" "$LOG_DIR/l2-functional.log" \
    env OPENVINCI_RUN_FUNCTIONAL=1 \
    "$PYTEST" "$ROOT/tests/functional"

# ---- L3 golden -------------------------------------------------------
run_level "L3 golden snapshot" "$LOG_DIR/l3-golden.log" \
    "$PYTEST" "$ROOT/tests/golden"

# ---- frontend (kept short — vitest is fast) -------------------------
if [ -n "$NPM" ] && [ -d "$ROOT/frontend/node_modules" ]; then
    run_level "frontend (vitest)" "$LOG_DIR/frontend.log" \
        bash -c "cd '$ROOT/frontend' && '$NPM' test --silent"
fi

# ---- report ---------------------------------------------------------
echo
echo "=========================================="
echo "OpenVinci Verification Report"
echo "=========================================="
for i in "${!LEVEL_NAMES[@]}"; do
    name="${LEVEL_NAMES[$i]}"
    result="${LEVEL_RESULTS[$i]}"
    dur="${LEVEL_DURATIONS[$i]}"
    printf "  [%-4s] %-28s %3ss\n" "$result" "$name" "$dur"
done
echo "------------------------------------------"
if [ "$OVERALL_RC" -eq 0 ]; then
    echo "  RESULT: PASS"
else
    echo "  RESULT: FAIL  (see logs under $(realpath --relative-to="$ROOT" "$LOG_DIR"))"
fi
echo "=========================================="

exit "$OVERALL_RC"
