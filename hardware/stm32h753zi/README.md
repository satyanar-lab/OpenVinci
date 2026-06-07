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

1. **PROMPT H1 (previous commit)** — get the arm-none-eabi-gcc
   cross-build working and prove the toolchain by booting a "hello"
   firmware that prints over the Nucleo's ST-LINK Virtual COM Port.
   **No CAN code yet.** This was the toolchain checkpoint.

2. **PROMPT H2 (this commit)** — drop the generated `*_Cfg.{h,c}` from
   `examples/com-minimal` onto the board, bring FDCAN1 up in
   internal-loopback mode, and link the same vendor/as Com / PduR /
   CanIf / mcal-Can sources the L2 host-sim node already proves. The
   cross-build links cleanly; real-silicon smoke is the next prompt.

## Current scope (PROMPT H2)

The firmware now boots and runs the full OpenVinci COM stack:

- `src/system_init.c` — brings PLL2Q up at 80 MHz (HSI64 → /8 → ×40 → /4)
  and routes it to the FDCAN kernel clock via `RCC.D2CCIP1R.FDCANSEL`.
- `src/main.c` — USART3 heartbeat, then the AUTOSAR init chain
  `Can_Init → CanIf_Init → PduR_Init → Com_Init`, then a 1 ms pump loop
  that calls `Com_SendSignal(TxSignal, …)` every ~100 ms and watches
  `Com_ReceiveSignal(RxSignal, …)` for changes.
- `src/Can_Cfg.{h,c}` — hand-written single-controller config; vendor
  `Can.c` reads it via `&Can_Config`.
- `src/Can_H7.c` — FDCAN1 backend implementing the `CanAc_*` contract
  from `vendor/as/infras/mcal/Can/Can_Priv.h` plus `Can_Write` and
  the `Can_MainFunction_Write/Read` pump:
  - INIT-mode entry/leave, NBTP for 500 kbit/s @ 87.5 % sample.
  - Message-RAM layout at `SRAMCAN_BASE`: Rx FIFO 0 (3 × 4 words) +
    one dedicated Tx Buffer (1 × 4 words). 8-byte payload (Classic
    CAN; FD support follow-up).
  - Internal loopback: `CCCR.TEST | CCCR.MON | TEST.LBCK`.
- `generated/` — `Com_Cfg`, `PduR_Cfg`, `CanIf_Cfg` produced by
  `tools/regenerate.py` from `examples/com-minimal`. Reproducible via
  `make generate`.

### Critical seam (`hoh` ↔ FDCAN buffer index)

The generated `CanIf_Cfg.c` sets every TxPdu / RxPdu `hoh` field to
**0**. We honour that everywhere:

| Layer                      | Object         | Value             |
| -------------------------- | -------------- | ----------------- |
| Generated CanIf            | `Hth`, `Hrh`   | `0`               |
| Our `Can_Cfg.c`            | channel 0      | `hwInstanceId 0`  |
| Our `Can_H7.c` Tx          | `Hth = 0`      | FDCAN1 Tx Buffer 0 |
| Our `Can_H7.c` Rx          | `Hrh = 0`      | FDCAN1 Rx FIFO 0  |

On Rx we deliver `Mailbox.Hoh = 0` to `CanIf_RxIndication` so the
generated CanIf does the same id-based dispatch the L2 host-sim test
already proves.

Output binary size:

```
   text    data    bss    dec    hex   filename
   6132      20   1580   7732   1e34   build/openvinci-h7.elf
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

# Regenerate the config from examples/com-minimal (uses the same
# backend/gen pipeline the desktop app calls). Outputs land in
# generated/. The committed files in this directory are bit-for-bit
# what this command produces.
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
files mean a cross-build alone needs only the C toolchain.

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

You should see (PROMPT H2 boot messages):

```
openvinci-h7: boot
openvinci-h7: stack up — sending TxSignal
```

After PROMPT H1's "hello" loop, the H2 firmware just emits two lines
during init and then runs the pump silently — the next prompt wires
an `RxSignal changed` print once a second sender lands.

## Source map

```
src/main.c            boot, USART3 heartbeat, AUTOSAR init + pump
src/system_init.c     PLL2Q → 80 MHz FDCAN kernel clock
src/Can_Cfg.c         single-controller config (vendor Can.c reads this)
src/Can_H7.c          FDCAN1 backend: CanAc_*, Can_Write, pump
include/Can_Cfg.h     macros + the `hoh` ↔ buffer-index seam, documented
generated/            *_Cfg.{h,c} produced by `tools/regenerate.py`
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
