# hardware/stm32h753zi — STM32H753ZI Nucleo-144 firmware

Isolated embedded-firmware area for running OpenVinci's generated
COM stack on a real **STM32H753ZI Nucleo-144** via FDCAN internal
loopback.

This directory is **separate** from the web/desktop application. None
of `make build` / `make run` / `make desktop-app` / `make verify`,
the `Dockerfile`, the PyInstaller `desktop.spec`, or
`scripts/verify.sh` reference anything under here — and they shouldn't.
The repo's `.dockerignore` explicitly excludes `hardware/`.

## Goal

Prove, on real silicon, the same OpenVinci-emitted CanIf → PduR → Com
path that L2 already proves on the host simulator:

1. **PROMPT H1 (committed)** — get the arm-none-eabi-gcc cross-build
   working and prove the toolchain by booting a "hello" firmware that
   prints over the Nucleo's ST-LINK Virtual COM Port. **No CAN code
   yet.** This was the toolchain checkpoint.

2. **PROMPT H2 (committed)** — drop the generated `*_Cfg.{h,c}` onto
   the board, bring FDCAN1 up in internal-loopback mode, and link the
   same vendor/as Com / PduR / CanIf / mcal-Can sources the L2 host-sim
   node already proves. Cross-build linked cleanly.

3. **PROMPT H3 (this commit)** — close the loop: send a `TxSignal`
   every ~100 ms and verify it round-trips through CanIf → PduR → Com
   on real silicon. The shared-id `examples/h7-loopback` config makes
   the looped frame actually deliver. CI now cross-compiles this
   firmware on every push.

## What this proves (and what it does NOT)

The on-board test exercises the **digital data path**:

```
Com_SendSignal(TxSignal)
   → PduR (Com → CanIf routing)
      → CanIf (Tx Pdu lookup)
         → vendor Can.c → our Can_H7.c → FDCAN1 Tx Buffer 0
            └── INTERNAL LOOPBACK (TEST.LBCK, no transceiver, no wire)
                → FDCAN1 Rx FIFO 0
   ← Can_H7.c → CanIf_RxIndication (canid-based dispatch)
      ← PduR (CanIf → Com routing)
         ← Com_RxIndication → Com_ReceiveSignal(RxSignal)
```

What it proves on real H7 silicon:
- The OpenVinci-generated `Com_Cfg` / `PduR_Cfg` / `CanIf_Cfg` are
  byte-identical to what the host-sim L2 tests already trust.
- A real MCAL (`vendor/as/infras/mcal/Can/Can.c` + our `Can_H7.c`)
  routes a frame end-to-end through that config.

What it does **not** prove:
- Physical bus signalling (no CAN transceiver wired, FDCAN1 stays
  inside the M_CAN core with `CCCR.MON | TEST.LBCK`).
- Multi-node arbitration / error handling.
- FD frames (we emit Classic CAN only; 8-byte payload).

Both gaps are deliberate — internal loopback is the smallest piece of
silicon that still distinguishes "the generator output works on real
hardware" from "the generator output works in a simulator."

## Current scope (PROMPT H3)

The firmware now boots and runs the full OpenVinci COM stack:

- `src/system_init.c` — brings PLL2Q up at 80 MHz (HSI64 → /8 → ×40 → /4)
  and routes it to the FDCAN kernel clock via `RCC.D2CCIP1R.FDCANSEL`.
- `src/main.c` — USART3 heartbeat, then the AUTOSAR init chain
  `Can_Init → CanIf_Init → PduR_Init → Com_Init`, then a 1 ms pump loop
  that calls `Com_SendSignal(TxSignal, …)` every ~100 ms and watches
  `Com_ReceiveSignal(RxSignal, …)` for changes.
- `generated/Can_Cfg.{h,c}` — single-controller driver config
  emitted by `backend/gen/can_h7.py` from the project tree. NBTP,
  MRAM layout, Rx filters (canid → Hrh), and Tx slots (Hth →
  buffer index) all come from this table at run-time. Vendor
  `Can.c` still reads `&Can_Config` from the same file.
- `src/Can_H7.c` — FDCAN1 backend implementing the `CanAc_*` contract
  from `vendor/as/infras/mcal/Can/Can_Priv.h` plus `Can_Write` and
  the `Can_MainFunction_Write/Read` pump. **Fully table-driven**
  (PROMPT C1): no message-specific or layout-specific constants live
  in the .c — everything flows in from `Can_H7_Config`. Internal
  loopback (`CCCR.TEST | CCCR.MON | TEST.LBCK`) stays on.
- `generated/{Com,PduR,CanIf}_Cfg.{h,c}` — vendor-generator output
  from `examples/h7-loopback`. The loopback example deliberately
  shares CAN id 0x100 between TX_MSG and RX_MSG so the looped frame
  is actually accepted by the generated CanIf Rx-Pdu lookup.
  Reproducible via `make generate`.

### Critical seam (`hoh` ↔ FDCAN buffer index)

The generated `CanIf_Cfg.c` sets every TxPdu / RxPdu `hoh` field to
**0**. We honour that everywhere:

| Layer                      | Object         | Value             |
| -------------------------- | -------------- | ----------------- |
| Generated CanIf            | `Hth`, `Hrh`   | `0`               |
| Generated `Can_Cfg.c`      | channel 0      | `hwInstanceId 0`  |
| Generated `Can_Cfg.c`      | `rxFilters[0]` | `canid=0x100, Hrh=0` |
| Generated `Can_Cfg.c`      | `txSlots[0]`   | `Hth=0, buffer=0`    |
| Driver `Can_H7.c` Tx       | `Hth = 0`      | FDCAN1 Tx Buffer 0 |
| Driver `Can_H7.c` Rx       | `Hrh = 0`      | FDCAN1 Rx FIFO 0  |

On Rx we deliver `Mailbox.Hoh = 0` to `CanIf_RxIndication` so the
generated CanIf does the same id-based dispatch the L2 host-sim test
already proves.

Output binary size:

```
   text    data    bss    dec    hex   filename
   6188      20   1580   7788   1e6c   build/openvinci-h7.elf
```

## Prerequisites

### Toolchain

- **arm-none-eabi-gcc** — tested on `13.2.1`. Install:

  ```sh
  # Debian / Ubuntu
  sudo apt install gcc-arm-none-eabi

  # macOS (Homebrew)
  brew tap ArmMbed/homebrew-formulae
  brew install arm-none-eabi-gcc

  # or download the ARM-provided tarball:
  # https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads
  ```

- A flashing tool — pick one:

  ```sh
  sudo apt install stlink-tools   # for `make flash`
  # or
  sudo apt install openocd        # for `make flash-openocd`
  ```

### Submodules

```sh
git submodule update --init \
    hardware/stm32h753zi/third_party/cmsis-device-h7 \
    hardware/stm32h753zi/third_party/CMSIS_5
```

`CMSIS_5` is large (~150 MB unpacked). `--depth 1` is already used for
both submodules in `.gitmodules`, so a fresh init grabs only the tip.

## Build + flash

```sh
cd hardware/stm32h753zi

# Regenerate the config from examples/h7-loopback (uses the same
# backend/gen pipeline the desktop app calls). Outputs land in
# generated/. The committed files in this directory are bit-for-bit
# what this command produces. Pass any other example name as an
# argument: `python3 tools/regenerate.py com-minimal`.
make generate

make            # → build/openvinci-h7.{elf,bin,hex}
make size       # arm-none-eabi-size summary

# Pick one of these to put it on the board:
make flash              # st-link tools (`st-flash write … 0x8000000`)
make flash-openocd      # OpenOCD (interface/stlink.cfg + target/stm32h7x.cfg)
```

`make generate` needs the backend's Python deps installed
(`pip install -e backend/` from the repo root, which pulls in `pycrc`
+ `scons` from `backend/pyproject.toml`). The committed `generated/`
files mean a cross-build alone needs only the C toolchain — and
that's the path CI takes (see `.github/workflows/firmware-cross-compile.yml`).

## Watch the UART

Connect the Nucleo's USB ST-LINK port to your host. The board appears
as a USB CDC ACM device:

| OS      | Device                                |
| ------- | ------------------------------------- |
| Linux   | `/dev/ttyACM0` (or higher if busy)    |
| macOS   | `/dev/cu.usbmodem*`                   |
| Windows | A new COM port (check Device Manager) |

Open at **115200 8N1, no flow control**:

```sh
screen /dev/ttyACM0 115200          # exit: Ctrl-A k
# or
picocom -b 115200 /dev/ttyACM0      # exit: Ctrl-A Ctrl-X
# or (Windows / VS Code)
# any serial monitor at 115200
```

You should see:

```
openvinci-h7: boot
openvinci-h7: stack up — sending TxSignal
openvinci-h7: RX=0x56
openvinci-h7: RX=0x57
openvinci-h7: RX=0x58
…
```

The two boot lines land during the init chain. After that, the pump
loop transmits `TxSignal = 0x55, 0x56, 0x57, …` every ~100 ms; the
internal-loopback path turns each into a CanIf Rx, PduR routes it
back to Com, and the next `Com_ReceiveSignal` poll prints the new
value as `RX=0xNN`.

**If you see the boot lines but no `RX=`**: the most common cause is
that `generated/CanIf_Cfg.c` was regenerated from a different example
(e.g. `com-minimal`, which uses Tx id 0x100 ≠ Rx id 0x101). Re-run
`make generate` (it defaults to `h7-loopback`) and reflash.

## Source map

```
src/main.c            boot, USART3 heartbeat, AUTOSAR init + pump
src/system_init.c     PLL2Q → 80 MHz FDCAN kernel clock
src/Can_H7.c          FDCAN1 backend: CanAc_*, Can_Write, pump
                      (table-driven against Can_H7_Config from C1)
generated/            All *_Cfg.{h,c} produced by `tools/regenerate.py`:
                      Com_Cfg / PduR_Cfg / CanIf_Cfg via the vendor
                      generator, Can_Cfg via backend/gen/can_h7.py.
tools/regenerate.py   wrapper around backend/gen/{stage,generate}.py
linker/
  stm32h753xx_flash.ld our linker script (upstream cmsis-device-h7
                       only ships dual-core H7 gcc linkers)
third_party/
  cmsis-device-h7/    STMicroelectronics device headers, gcc startup,
                      and system_stm32h7xx.c (submodule)
  CMSIS_5/            ARM CMSIS-Core Cortex-M7 headers (submodule)
build/                cross-build outputs (gitignored)
```

The vendor BSW (`vendor/as/infras/communication/{Com,PduR,CanIf}/*.c`
and `vendor/as/infras/mcal/Can/Can.c`) is pulled in directly by the
Makefile — these are the **same sources** the L2 functional tests
already exercise on the host simulator.

## What this is NOT

- It is **not** part of the Python backend. `backend/pyproject.toml`'s
  package allowlist doesn't include `hardware*`.
- It is **not** in the Docker image. The `Dockerfile` doesn't COPY
  it and `.dockerignore` excludes the whole directory.
- It is **not** in the PyInstaller bundle. `desktop.spec` only lists
  `frontend/dist`, `model`, `examples`, and `vendor/as/{tools,infras}`
  as `datas`.
- It is **not** in `scripts/verify.sh` or any `make` target outside
  this directory. The cross-build is opt-in: you build it from inside
  `hardware/stm32h753zi/` or not at all.
