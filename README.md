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
