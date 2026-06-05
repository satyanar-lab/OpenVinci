# tests/functional — VERIFICATION LEVEL 2

End-to-end functional loopback through `vendor/as`'s host CAN
simulator. Builds artifacts on the fly with `gcc`/`g++` and exercises
the same TCP wire protocol that the simulator-platform `Can.cpp`
driver speaks at runtime.

## Run

```sh
OPENVINCI_RUN_FUNCTIONAL=1 .venv/bin/pytest tests/functional -v
```

Without the env var the suite skips cleanly so it doesn't slow down
the unit suite or break in CI environments without a build
toolchain.

## What it verifies today

`TestBrokerLoopback` builds `vendor/as`'s `can_simulator` directly
via `gcc` (no scons → no `gitee.com` mirrors for `mbedtls` / lua / …
that the heavy upstream build pulls in) and proves the runtime wire
protocol that the simulator-platform driver expects:

- the broker starts and accepts TCP clients on `127.0.0.1:8000+busId`,
- a frame sent by one client reaches every other client byte-exactly,
- the broker correctly suppresses the echo back to the sender,
- multiple in-flight IDs are routed correctly.

That's the same protocol `app/platform/simulator/src/Can.cpp` uses
via `tools/libraries/Can/src/simulator_can.cpp`. Verification level 1
proves the generated configs are syntactically + structurally valid
for that driver; this test proves the runtime they will sit on top of
actually transports data.

## What it doesn't (yet) verify

`TestComStackLoopback` is the stretch goal: a minimal node binary
that links `Com.c` + `CanIf.c` + `PduR.c` + the simulator `Can.cpp`
with our generated `*_Cfg.c` files, then `Com_SendSignal` /
`Com_MainFunction_Tx` actually pushes a frame onto the bus and
`Com_RxIndication` fires for injected frames. The class is wired and
ready; the `node_binary` fixture skips today because:

1. Upstream's `scons --app=CanApp` pulls `mbedtls`, `libtommath`,
   `libtomcrypt`, and `lua` from gitee mirrors that aren't reachable
   from this environment (gitee requires auth that the build doesn't
   provide). The github mirrors are reachable; `AS_DOWNLOAD_DIR`
   pre-population works but the build then hits the AsPy/AsOne
   shared-library chain which also depends on these.

2. A custom minimal node compiled directly with `gcc` needs to wire
   up Os/EcuM/Mcu init the way `app/platform/simulator/src/simulator.c`
   does — workable but adds enough surface that we deferred it from
   this commit.

When either path is unblocked, the `node_binary` fixture becomes
real and `TestComStackLoopback` runs without further test code
changes.
