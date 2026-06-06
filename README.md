# OpenVinci

An open-source, developer-focused configurator for the **AUTOSAR Classic
COM stack**. Inspired by Vector DaVinci Configurator, built on top of
[`autoas/as`](https://github.com/autoas/as) — a complete open-source
AUTOSAR 4.4 BSW implementation by Parai Wang.

What you get:

- A **DaVinci-style 3-pane web UI** (modules / containers / parameters
  tree, schema-driven typed editor with cross-reference dropdowns,
  live Problems panel with one-click auto-fixes).
- **Communication-matrix import** — drop a `.dbc`, get a fully wired
  project (Com, CanIf, PduR, Can) in one call.
- **Generate + compile in one step** — emits the upstream
  `*_Cfg.{h,c}` and verifies them against the BSW headers.
- **A four-level verification report** (`scripts/verify.sh`) that
  states exactly what we've proven — and what we haven't.

OpenVinci doesn't replace `autoas/as`. It wraps it. Every JSON file
OpenVinci edits is the same shape `vendor/as`'s generators already
consume; you can drop an OpenVinci project into a checkout of
`autoas/as` and `scons --app=CanApp` without changing a byte.

## Upstream license note (read this before commercial use)

`autoas/as` is dual-licensed under **GPLv3 and a separate commercial
license** by Parai Wang. The upstream README states the project is
"only free to be used for evaluation and study purpose." OpenVinci
vendors the source as a git submodule under [`vendor/as`](vendor/as)
and does not relicense it.

- **Evaluation / study / personal exploration**: fine under the
  upstream's terms.
- **Anything else** (shipping a product that links to or generates
  from `vendor/as`, distributing derived BSW code, etc.): you need
  to either comply with GPLv3 yourself or contact Parai Wang at
  `parai@foxmail.com` for a commercial license.

OpenVinci itself is MIT-licensed (see `LICENSE` once added) — but
that doesn't change `autoas/as`'s terms. The licenses compose; the
stricter one wins.

## Quick start

```sh
git submodule update --init  # see CI notes if recursive trips on qemu
make install                  # python venv + npm install
make test                     # pytest + vitest (~3s)
make dev                      # backend :8000, frontend :5173 (Ctrl+C kills both)
```

Open <http://localhost:5173>. The UI loads `examples/com-minimal` by
default. Try:

1. **Import DBC** → drop any of the 11 DBCs in `examples/dbc/` onto
   the drop zone (or pick a bundled one). Watch the tree fill in.
2. Select a Com signal in the tree; edit `factor` or `offset`.
3. **Generate** → see a green compile status with file list.
4. Open the **Problems** panel after a deliberate break (e.g. delete
   a Can controller) and click **Fix** — the engine re-wires it.

For a scripted, headless version of that walkthrough, see
[`docs/DEMO.md`](docs/DEMO.md) and run:

```sh
scripts/demo.sh
```

## Run in Docker (toolchain + submodule travel with the image)

A multi-stage `Dockerfile` at the repo root produces a single image
that bundles **the same gcc / generator / vendor/as combination** the
local `make verify` runs against — so anyone with Docker can reproduce
the L1 generate+compile chain without setting up Python, Node, or a
build toolchain.

Prerequisite: the `autoas/as` submodule must be initialised so its
sources are part of the Docker build context. The Dockerfile copies
straight from the context — no `git submodule` at image-build time
(this is intentional so an offline build with a vendored tarball
works the same way):

```sh
git submodule update --init vendor/as
docker build -t openvinci .
docker run --rm -p 8000:8000 openvinci   # then open http://localhost:8000
```

That gives you the same SPA + APIs the `make run` single-process
flow does, on port 8000.

### Verify the toolchain inside the container

Prove the gcc + vendor/as pair really travels with the image, not
just the binary:

```sh
# L1 generate+compile (gcc -c -fsyntax-only against vendor/as headers,
# from the L1 verification level — the most representative single
# check that the toolchain works end-to-end)
docker run --rm openvinci pytest -q backend/tests/test_gen_pipeline.py

# Or the full report:
docker run --rm -e OPENVINCI_RUN_FUNCTIONAL=1 openvinci scripts/verify.sh
```

The container runs as a non-root user (`openvinci`, uid 1000), sets a
no-coredump ulimit at entry, and caps the gcc subprocess at 30s
(override with `-e OPENVINCI_GCC_TIMEOUT_S`). Body size on
`/api/generate` is capped at 20 MB (override with
`-e OPENVINCI_MAX_BODY_BYTES`).

## Repository layout

```
backend/           FastAPI service: model layer (Pydantic), engine
                   (validation + derivation + solver), gen adapter
                   (vendor/as wrapper + gcc compile check), DBC importer.
frontend/          React + Vite + TS UI (DaVinci-style 3-pane).
model/             JSON Schemas for each `class` (Can, CanIf, CanTp,
                   PduR, Com) + shared $defs.
examples/          Real autoas/as configs used as fixtures.
  canapp-min/      Mirror of vendor/as/app/app/config (round-trip fixture).
  com-minimal/     Minimal generate+compile-clean project (L1/L3 fixture).
  dbc/             Sample DBCs — synthetic + curated subsets of
                   cantools and opendbc (MIT). See examples/dbc/README.md.
tests/
  functional/      VERIFICATION LEVEL 2 — pytest + vendor/as CAN broker.
  golden/          VERIFICATION LEVEL 3 — snapshot regression.
scripts/
  verify.sh        Run all verification levels, print PASS/FAIL report.
  demo.sh          Headless happy-path walkthrough.
vendor/as/         autoas/as git submodule.
docs/
  AUTOAS_NOTES.md  Verified facts about the upstream config + build chain.
  ARCHITECTURE.md  The four-layer design.
  DEMO.md          5-minute walkthrough.
```

Top-level conventions and per-layer notes live in [`CLAUDE.md`](CLAUDE.md).

## How generated files are verified

OpenVinci ships seven verification levels. Each one makes a *specific*
claim. Together they say: the configs OpenVinci emits are
**structurally valid, syntactically + semantically valid C against the
BSW headers, byte-stable across regenerations, transported byte-exact
by the runtime simulator, and — when linked into a real node — route
classic Com signals, FD-sized PDUs, and ISO-15765 segmented diagnostic
SDUs end-to-end through the generated CanIf→PduR→{Com, CanTp→Dcm}
paths.**

That is precisely what they say. It is **not** what they don't say —
see the disclaimer below.

| Level | Test target | Concrete claim |
|------|---|---|
| **L1 validate** | `make test-backend` | Every example loads through the typed model, round-trips serializer ↔ JSON without drift, validates against the Layer-1 JSON Schemas (Draft 2020-12), and passes every engine rule (cross-module reference integrity, multiplicity, type/range). The DBC matrix (`test_dbc_matrix.py`) parametrizes over every file in `examples/dbc/` — parse → import → validate → generate+compile, ~190 tests in total. |
| **L1 generate+compile** | `pytest backend/tests/test_gen_pipeline.py` | The upstream `vendor/as` generators emit `*_Cfg.{h,c}` from our project that parses cleanly with `gcc -c -fsyntax-only -Wall` against the BSW headers in `vendor/as/infras/communication/`. Catches syntax errors, type mismatches with the BSW, missing struct fields, missing includes. |
| **L2 broker transport** | `make test-functional` (TestBrokerLoopback) | `vendor/as`'s `can_simulator` broker — the same TCP wire protocol the simulator-platform `Can.cpp` driver speaks at runtime — comes up, accepts clients, transports frames byte-exact between peers, and correctly suppresses sender echoes. The wire layer the rest of L2 sits on actually works. |
| **L2 end-to-end (generated stack)** | `make test-functional` (TestComStackLoopback) | A real node binary is built by gcc-linking our generated `*_Cfg.c` (from `examples/com-minimal`) with the upstream Com / CanIf / PduR / Can MCAL sources plus the simulator Can driver. With that node running: (a) `Com_SendSignal(COM_SID_TxSignal, …)` on the generated config becomes a CAN frame at id `0x100` that the broker routes to a Python listener, and (b) a `0x101` frame the harness injects is decoded by the generated `CanIf → PduR_CanIfRxIndication → PduR_RxIndication → Com_RxIndication` path, and `Com_ReceiveSignal(COM_SID_RxSignal, …)` returns the exact byte the harness sent. The OpenVinci-emitted config wires real data through the upstream stack. |
| **L2 end-to-end CAN FD (generated stack)** | `make test-functional` (TestCanFdLoopback) | Same chain, against `examples/canfd-minimal`: an FD-marked PDU (`fd: true`, `dlc: 16`) with a 16-byte `UINT8N` signal on each direction. With the FD node running: (a) `Com_SendSignal(COM_SID_TxFdSignal, …)` becomes a wire frame at id `0x200` whose dlc field equals **16** and whose 16 payload bytes equal the bytes the node Com-sent — anything narrower would silently pass the classic check. (b) The harness injects a known 16-byte payload at id `0x201`; the generated `CanIf → PduR_CanIfRxIndication → PduR_RxIndication → Com_RxIndication` path populates the FD Com IPDU, and `Com_ReceiveSignal(COM_SID_RxFdSignal, …)` returns **all 16 bytes** byte-exact. FD-sized PDU routing through the OpenVinci-emitted Com/CanIf/PduR config + upstream BSW is real, not stubbed. |
| **L2 end-to-end CanTp segmented (generated stack)** | `make test-functional` (TestCanTpLoopback) | ISO-15765 segmented diagnostic transport against `examples/cantp-iso15765`. The node is built from a Com-less project (CanIf + PduR + CanTp + a Dcm upper-layer sink). The Python harness only speaks raw ISO-TP PCI frames at the CanIf RxPdu id `0x7e0`: (a) a 5-byte SDU is sent as a Single Frame and the sink logs `DcmRx[5]=<exact hex>` via `Dcm_TpRxIndication`. (b) A 20-byte SDU is sent as `FF` + (await `FC` from node on `0x7e8` — asserted) + 2× `CF` (SN=1, SN=2); the sink logs `DcmRx[20]=<exact 20 bytes>`. (c) Negative case: a deliberate CF sequence-number gap (SN=1, SN=3) must produce **no** success log — upstream CanTp's sequence guard (`CanTp.c:425-428`) stays enforced. Segmentation / reassembly is **only** in upstream `CanTp.c`; the sink does nothing but memcpy + print. |
| **L3 golden snapshot** | `make test-golden` | The exact byte content of every generated file (modulo the vendor/as timestamp lines we strip) matches a checked-in snapshot, for `com-minimal`, `canfd-minimal`, and `cantp-iso15765`. Any unintended drift in the generator chain, the model serializer, or our staging fails immediately. Rebaseline with `pytest tests/golden --update-golden`. |

Run them all:

```sh
make verify
```

prints a per-level report and exits non-zero if any level fails.
CI runs this on every push — see
[`.github/workflows/verify.yml`](.github/workflows/verify.yml).

### What these levels do NOT claim

**OpenVinci is not production-, hardware-, or safety-certified.** Read
this carefully:

- L1 + L2 + L3 prove the configs OpenVinci produces are *valid input*
  to the BSW source code in `vendor/as` and that a CAN simulator
  routes frames. None of them prove the resulting code is correct
  for any specific ECU, MCU, or AUTOSAR-conformance suite.
- The host simulator (`vendor/as/app/platform/simulator/`) is a
  **PC-side mock** of CAN hardware. Behaviour on a real Cortex-M /
  PowerPC / TriCore target can and will differ — bit timing,
  arbitration, mailbox allocation, interrupt latencies, real-time
  scheduling assumptions, etc.
- ISO 26262 / ASIL functional-safety claims, AUTOSAR conformance
  certification, MISRA-C compliance audits — none of these are
  exercised by these tests, and none are claimed by the project.
- A successful L2 end-to-end (classic + FD + CanTp) says "for these
  configured PDUs, on these configured signals, the generated
  CanIf→PduR→Com path round-trips a single byte (classic,
  `examples/com-minimal`) and a 16-byte UINT8N payload (FD,
  `examples/canfd-minimal`), and the generated CanIf→CanTp→PduR→Dcm
  path round-trips a 20-byte segmented SDU
  (CanTp, `examples/cantp-iso15765`), through the upstream BSW on a
  host simulator." It does not say "your Dcm session-control state
  machine handles 0x10 03 correctly," "your CanNm wake-up signalling
  is spec-conformant," or "your generated E2E checksums match what
  the OEM expects." Higher layers (real Dcm services, CanNm, SecOC,
  E2E, COM groups, signal gateways, …) are not exercised — not yet
  linked, not yet verified. Multi-signal, multi-message, and
  multi-network coverage past the three minimal fixtures is on the
  user.
- **CanTp specifically.** L2 CanTp proves *segmented-SDU routing* on
  a host simulator with the classic-CAN single-block-no-STmin
  configuration we ship in `examples/cantp-iso15765`: SF for short
  SDUs, FF + a single FC + CF train for longer ones. It does NOT
  exercise: extended-addressing N_TA, FD-sized LL_DL (`LL_DL > 8`),
  multi-block STmin pacing under load, wait-frame retry loops,
  N_As/N_Bs/N_Cr timeout abort paths against a misbehaving peer, or
  the Tx direction (`CanTp_Transmit` from the upper layer). The
  schema (`model/cantp.schema.json`) already accepts these knobs;
  proving them at L2 is future work.
- **CAN FD specifically.** L2 FD proves *FD-sized PDU routing* on a
  host simulator (broker + simulator Can driver), not FD bit-rate
  switching (BRS), FD data-phase timing, or arbitration-phase /
  data-phase sample-point split. Those parameters live in the
  hand-written `Can_Cfg.c` of the MCAL — which OpenVinci does NOT
  generate (see `docs/AUTOAS_NOTES.md` §1.2 — there is no upstream
  `Can` generator) and the host simulator does not model. On real CAN
  FD hardware the upstream `CanIf.py` generator also strips the
  `CAN_CANFD_ID_TYPE` (0x40000000) bit from canids (`vendor/as/tools/
  generator/CanIf.py:115, :134-135, :253-254`); OpenVinci preserves the
  intent in the `fd: true` flag at the config level but does not yet
  re-inject the bit at the generator hand-off. See
  `docs/CANFD_FEASIBILITY.md` §4.
- The upstream `autoas/as` BSW is itself a study project (see the
  license note above). It is not a tier-1 supplier's
  series-production AUTOSAR stack.

Use OpenVinci to learn the AUTOSAR COM stack, to prototype
configurations, to bring up host-PC simulations, and to drive
DBC-derived integration tests. **Do not** deploy what it generates to
a vehicle without an independent, certification-grade verification
chain on top.

## Docs

- [`docs/DEMO.md`](docs/DEMO.md) — five-minute walkthrough.
- [`docs/AUTOAS_NOTES.md`](docs/AUTOAS_NOTES.md) — verified facts
  about the upstream config formats, generators, and host-sim build
  chain. Every claim cites a file path inside `vendor/as`.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the four-layer
  design (JSON Schema model, headless engine, generation adapter,
  React UI).
- [`CLAUDE.md`](CLAUDE.md) — repo conventions, all `make` targets,
  and the gotchas you'd otherwise rediscover the hard way (system
  `PYTHONPATH` from ROS leaking into the venv, `vendor/as`'s
  hardcoded gitee mirrors, etc.).

## API surface (backend)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/schemas` | Bundle of Layer-1 JSON Schemas |
| GET | `/schemas/{cls}` | One schema |
| GET | `/api/projects` | List bundled example projects |
| GET | `/api/projects/{name}` | Full project (every module) |
| GET | `/api/config?project=&module=` | Single module file |
| POST | `/api/validate` | Body: `{project}`; runs engine; returns issues + fixes |
| POST | `/api/apply-fix` | Body: `{project, fix}`; applies one auto-fix; returns updated project + report |
| GET | `/api/dbcs` | List bundled DBC files |
| POST | `/api/import/dbc?dbc=&network=&me=` | DBC → fully wired project |
| POST | `/api/generate` | Body: `{project, sourceProject?}`; stages → generates → compile-checks; returns files + diagnostics |

## CLI

```sh
openvinci-import-dbc examples/dbc/sample.dbc --out /tmp/myproject \
    --network CAN0 --me AS
```

Parses the DBC, auto-wires PduR/CanIf/Can, writes the four modeled
module JSONs into `--out` using vendor/as's expected layout. See
`docs/DEMO.md` for the full workflow.

## License

OpenVinci's own code is under the MIT License (see [`LICENSE`](LICENSE)
when added). The vendored `autoas/as` submodule is **GPLv3 + commercial**
by Parai Wang — see the "Upstream license note" above before commercial use.
