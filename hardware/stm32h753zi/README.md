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

1. **PROMPT H1 (this commit)** — get the arm-none-eabi-gcc cross-build
   working and prove the toolchain by booting a "hello" firmware that
   prints over the Nucleo's ST-LINK Virtual COM Port. **No CAN code
   yet.** This is the toolchain checkpoint.

2. **PROMPT H2 (next)** — drop the generated `*_Cfg.{h,c}` from one of
   OpenVinci's example projects onto the board, set FDCAN1 in
   internal-loopback mode, and prove a single
   `Com_SendSignal → CanIf → FDCAN → CanIf_RxIndication → Com_RxIndication
   → Com_ReceiveSignal` round-trip — same shape as the L2 host-sim test,
   but with the BSW driving real silicon.

## Current scope (PROMPT H1)

The firmware in `src/main.c` does only:

- Boots from cmsis-device-h7's `Reset_Handler` (FLASH @ 0x08000000).
- Runs `SystemInit()` (default clock — HSI 64 MHz, no PLL).
- Enables GPIOD + USART3, configures `PD8`/`PD9` as AF7.
- Loops printing `hello\r\n` at 115200 8N1 over the on-board ST-LINK
  Virtual COM Port.

Output binary size:

```
   text    data    bss    dec    hex   filename
   1484       0   1536   3020    bcc   build/stm32h753zi-hello.elf
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

make            # → build/stm32h753zi-hello.{elf,bin,hex}
make size       # arm-none-eabi-size summary

# Pick one of these to put it on the board:
make flash              # st-link tools (`st-flash write … 0x8000000`)
make flash-openocd      # OpenOCD (interface/stlink.cfg + target/stm32h7x.cfg)
```

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
hello
hello
hello
...
```

…printing roughly once per second.

## Source map

```
src/main.c            this firmware — clock + USART3 init + print loop
linker/
  stm32h753xx_flash.ld our linker script (upstream cmsis-device-h7
                       only ships dual-core H7 gcc linkers)
third_party/
  cmsis-device-h7/    STMicroelectronics device headers, gcc startup,
                      and system_stm32h7xx.c (submodule)
  CMSIS_5/            ARM CMSIS-Core Cortex-M7 headers (submodule)
build/                cross-build outputs (gitignored)
```

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
