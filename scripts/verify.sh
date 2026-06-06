#!/usr/bin/env bash
# OpenVinci verification — run every level in order, print a single report.
#
# Levels:
#   1. validate              — model + engine unit tests (round-trip,
#                              schema, validation rules, derive, solve)
#   2. generate+compile      — gen pipeline: stage → vendor/as
#                              generators → gcc -c -fsyntax-only
#                              against BSW headers
#   3. broker transport      — vendor/as can_simulator broker, raw
#                              socket frame transport with byte-exact
#                              fidelity (TestBrokerLoopback)
#   4. end-to-end (generated
#      stack)                — gcc-link the generated *_Cfg.c with
#                              Com.c / CanIf.c / PduR.c / mcal-Can.c
#                              + simulator Can driver, drive its Tx
#                              and Rx CLI modes, and assert a single
#                              byte round-trips end-to-end through the
#                              generated CanIf→PduR→Com path
#                              (TestComStackLoopback)
#   5. end-to-end CAN FD     — same chain, against examples/canfd-
#      (generated stack)       minimal: 16-byte UINT8N signal on an
#                              FD-marked PDU (dlc=16). Asserts the
#                              broker sees a 16-byte frame at id 0x200
#                              with the exact bytes the node
#                              Com_SendSignal'd, and that
#                              Com_ReceiveSignal returns all 16 bytes
#                              of an injected 0x201 frame byte-exact
#                              (TestCanFdLoopback)
#   6. end-to-end CanTp      — segmented diagnostic transport against
#      segmented (generated     examples/cantp-iso15765. Harness acts
#      stack)                   as ISO-15765 peer: SF for a 5-byte SDU
#                              and FF + (await FC from node) + 2× CF
#                              for a 20-byte SDU. CanTp.c reassembles;
#                              the Dcm sink prints byte-exact bytes via
#                              Dcm_TpRxIndication. A third test asserts
#                              that a CF SN discontinuity must NOT
#                              produce a success log (TestCanTpLoopback)
#   7. golden                — regenerate, normalize timestamps,
#                              byte-diff against
#                              tests/golden/<example>/expected/
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

# ---- L2 broker transport --------------------------------------------
# Just the wire-protocol layer: TestBrokerLoopback. The broker fixture
# builds vendor/as's can_simulator and asserts it forwards frames
# byte-exact between Python clients. This proves nothing about our
# generated config — that's L2 end-to-end, next.
run_level "L2 broker transport" "$LOG_DIR/l2-broker.log" \
    env OPENVINCI_RUN_FUNCTIONAL=1 \
    "$PYTEST" "$ROOT/tests/functional/test_loopback.py::TestBrokerLoopback"

# ---- L2 end-to-end (generated stack) --------------------------------
# The real claim: gcc-link the *_Cfg.c generated from com-minimal with
# Com.c / CanIf.c / PduR.c / mcal-Can.c + the simulator Can driver,
# then drive the node through its Tx and Rx CLI modes. A Tx assertion
# (id 0x100 appears on the bus) and an Rx assertion (Com_ReceiveSignal
# returns the exact byte the harness injected on 0x101) close the
# loop end-to-end through the generated CanIf→PduR→Com path.
run_level "L2 end-to-end (generated stack)" "$LOG_DIR/l2-e2e.log" \
    env OPENVINCI_RUN_FUNCTIONAL=1 \
    "$PYTEST" "$ROOT/tests/functional/test_loopback.py::TestComStackLoopback"

# ---- L2 end-to-end CAN FD (generated stack) -------------------------
# Sister of L2 end-to-end, run against examples/canfd-minimal: a
# 16-byte UINT8N signal rides an FD-marked PDU with dlc=16. The Tx
# assertion now also checks the wire dlc field (==16) and that the
# 16-byte payload matches what the node Com_SendSignal'd byte-for-byte
# — anything narrower would silently pass the classic-CAN check above.
# The Rx assertion is symmetric: 16 known bytes injected at id 0x201,
# and Com_ReceiveSignal must return all 16 byte-exact.
run_level "L2 end-to-end CAN FD (generated stack)" "$LOG_DIR/l2-e2e-canfd.log" \
    env OPENVINCI_RUN_FUNCTIONAL=1 \
    "$PYTEST" "$ROOT/tests/functional/test_loopback.py::TestCanFdLoopback"

# ---- L2 end-to-end CanTp segmented (generated stack) ----------------
# The diagnostic-transport sister, run against examples/cantp-iso15765.
# A 20-byte SDU is sent by the Python harness as ISO-15765 frames:
# FF + 2× CF, with the node's CanTp.c sending the intermediate FC on
# 0x7E8 (asserted). All segmentation lives in upstream CanTp.c — the
# Dcm sink (node_tp_sink.c) only memcpys + prints what
# Dcm_TpRxIndication(E_OK) hands it. A third test deliberately skips a
# CF and asserts no success line appears: upstream sequence guards must
# stay enforced.
run_level "L2 end-to-end CanTp segmented (generated stack)" "$LOG_DIR/l2-e2e-cantp.log" \
    env OPENVINCI_RUN_FUNCTIONAL=1 \
    "$PYTEST" "$ROOT/tests/functional/test_loopback.py::TestCanTpLoopback"

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
