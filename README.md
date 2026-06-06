# OpenVinci

An open-source, developer-focused configurator for the AUTOSAR Classic
COM stack, built on top of [`autoas/as`](https://github.com/autoas/as).

## Docs

- [`docs/AUTOAS_NOTES.md`](docs/AUTOAS_NOTES.md) — verified facts about
  the upstream config formats, generators, and host-sim build chain.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the four-layer design.
- [`CLAUDE.md`](CLAUDE.md) — repo conventions and build/test commands.

## Layout

```
backend/    FastAPI service (Layer 2 + 3)
frontend/   React + Vite + TypeScript app (Layer 4)
model/      JSON Schemas (Layer 1)              — placeholder for now
examples/   Real autoas/as configs used as fixtures + smoke tests
vendor/as/  autoas/as as a git submodule
```

## Quick start

```sh
git submodule update --init --recursive
make install         # python venv + npm install
make test            # pytest + vitest
make dev             # backend on :8000, frontend on :5173 (Ctrl+C kills both)
```

Open http://localhost:5173 — the page shows the `Com.json` from
`examples/canapp-min/` loaded via the backend's stub `/api/config`.

## Verification levels

```sh
make verify     # runs L1 (validate + generate+compile) + L2 (functional) + L3 (golden)
```

Prints a per-level pass/fail report. Each level is also independently runnable:

| Level | Target | What it proves |
|-------|--------|----------------|
| L1 validate | `make test-backend` | Round-trip fidelity, schema validation, engine rules, derive, solve |
| L1 generate+compile | `pytest backend/tests/test_gen_pipeline.py` | Generated `*_Cfg.c` parses cleanly against `vendor/as` BSW headers |
| L2 functional loopback | `make test-functional` | `vendor/as`'s CAN simulator broker transports frames byte-exact end-to-end |
| L3 golden snapshot | `make test-golden` | Generated output matches checked-in snapshot under `tests/golden/<example>/expected/`. Rebaseline with `pytest tests/golden --update-golden`. |

CI runs `scripts/verify.sh` on every push (`.github/workflows/verify.yml`).

## Generate + compile (VERIFICATION LEVEL 1)

```sh
curl -X POST 'http://localhost:8000/api/generate?project=com-minimal'
```

Stages the project to a tempdir, invokes the upstream `vendor/as`
generators to produce `*_Cfg.{h,c}`, then `gcc -c -fsyntax-only`s
each generated `.c` against the BSW headers in
`vendor/as/infras/communication/`. Returns `{files, compileResult}`
with all parsed diagnostics; the `pytest`
`tests/test_gen_pipeline.py::test_compile_is_clean` asserts a clean
build of `examples/com-minimal`.
