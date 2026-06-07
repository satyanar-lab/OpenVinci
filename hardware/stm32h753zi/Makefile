# Cross-build for STM32H753ZI Nucleo-144 — OpenVinci COM stack on FDCAN1
# in internal loopback.
#
# What this builds (PROMPT H2):
#   - cmsis-device-h7's startup_stm32h753xx.s + system_stm32h7xx.c
#   - src/main.c        — boot, USART3 heartbeat, AUTOSAR init + pump
#   - src/Can_Cfg.c     — single-controller config the vendor MCAL reads
#   - src/Can_H7.c      — FDCAN1 backend (CanAc_*, Can_Write, pump)
#   - src/system_init.c — PLL2Q → 80 MHz FDCAN kernel clock
#   - generated/*.c     — OpenVinci-generated Com_Cfg / PduR_Cfg / CanIf_Cfg
#   - vendor/as BSW     — the SAME Com.c / PduR*.c / CanIf.c / Can.c the
#                         host-sim L2 tests already prove
#
# Cross-compile only — the bar for PROMPT H2 is "links clean with
# arm-none-eabi-gcc". Real-silicon flash + smoke is a follow-up prompt.
#
# This Makefile is intentionally isolated from the repo's top-level
# Makefile — none of `make build` / `make run` / `make desktop-app` /
# `make verify` reference this directory. Run from inside
# hardware/stm32h753zi/:
#
#     make generate       # python3 tools/regenerate.py → generated/
#     make                # → build/openvinci-h7.{elf,bin}
#     make flash          # st-flash write build/openvinci-h7.bin 0x8000000
#     make flash-openocd
#     make clean
#     make size           # arm-none-eabi-size summary

PROJECT     := openvinci-h7

# Cross toolchain — apt: gcc-arm-none-eabi. Override with `make
# CROSS=...` if your toolchain prefix differs (e.g. local builds in
# /opt/gcc-arm/bin/arm-none-eabi-).
CROSS       ?= arm-none-eabi-
CC          := $(CROSS)gcc
OBJCOPY     := $(CROSS)objcopy
SIZE        := $(CROSS)size

# Layout
SRC_DIR     := src
INC_DIR     := include
GEN_DIR     := generated
LINKER_DIR  := linker
BUILD_DIR   := build

# Submodules. Cloned via:
#   git submodule update --init \
#     hardware/stm32h753zi/third_party/cmsis-device-h7 \
#     hardware/stm32h753zi/third_party/CMSIS_5
THIRD_PARTY := third_party
CMSIS_CORE  := $(THIRD_PARTY)/CMSIS_5/CMSIS/Core/Include
CMSIS_DEV   := $(THIRD_PARTY)/cmsis-device-h7
DEV_INC     := $(CMSIS_DEV)/Include
DEV_TPL     := $(CMSIS_DEV)/Source/Templates

# Device-specific files
STARTUP_S   := $(DEV_TPL)/gcc/startup_stm32h753xx.s
SYSTEM_C    := $(DEV_TPL)/system_stm32h7xx.c
LDSCRIPT    := $(LINKER_DIR)/stm32h753xx_flash.ld

# Vendor BSW (autoas/as submodule, mounted at repo root). All paths
# are relative to this Makefile, hence the `../../vendor/as/` prefix.
VENDOR_AS   := ../../vendor/as
BSW_DIR     := $(VENDOR_AS)/infras

# BSW C sources we link in. Mirror tests/functional/conftest.py's
# `_NODE_BASE_C_SRC_REL` + `_NODE_COM_C_SRC_REL` lists — same files
# the L2 host-sim node already builds and round-trips against the
# OpenVinci-generated Com_Cfg / PduR_Cfg / CanIf_Cfg.
#
# Excluded vs. the host-sim list:
#   * std_timer.c — host-only (clock_gettime / Windows mmsystem) and
#     none of Com / PduR / CanIf / Can reference Std_Timer symbols
#     directly, so dropping it keeps the link clean.
#   * TcpIp / app/platform/simulator — host broker shims that have no
#     counterpart on bare metal.
BSW_C       := \
    $(BSW_DIR)/communication/Com/Com.c \
    $(BSW_DIR)/communication/PduR/PduR.c \
    $(BSW_DIR)/communication/PduR/PduR_Com.c \
    $(BSW_DIR)/communication/PduR/PduR_CanIf.c \
    $(BSW_DIR)/communication/CanIf/CanIf.c \
    $(BSW_DIR)/mcal/Can/Can.c \
    $(BSW_DIR)/libraries/stdbit/src/std_bit.c \
    $(BSW_DIR)/libraries/mempool/mempool.c

# Include search paths the BSW expects. Same set the host-sim build
# uses, minus the host-only dirs.
BSW_INC     := \
    -I$(BSW_DIR)/include \
    -I$(BSW_DIR)/mcal/Can \
    -I$(BSW_DIR)/communication/Com \
    -I$(BSW_DIR)/communication/CanIf \
    -I$(BSW_DIR)/communication/PduR \
    -I$(BSW_DIR)/libraries/stdbit/src \
    -I$(BSW_DIR)/libraries/mempool

# Generated *_Cfg.c files. tools/regenerate.py drops them here.
GEN_C       := $(wildcard $(GEN_DIR)/*.c)

# Cortex-M7F (FPU, hard-float ABI to match what cmsis-device-h7's
# startup is compiled for).
ARCH_FLAGS  := -mcpu=cortex-m7 -mthumb \
               -mfpu=fpv5-d16 -mfloat-abi=hard

# Module-enable knobs the BSW source reads via `#ifdef USE_*`. Must
# match what `tests/functional/conftest.py` passes (lines 298–304) so
# the same code paths compile in.
DEFS        := -DSTM32H753xx \
               -DUSE_CAN -DUSE_CANIF -DUSE_PDUR -DUSE_COM

INC_FLAGS   := -I$(CMSIS_CORE) -I$(DEV_INC) \
               -I$(INC_DIR) -I$(GEN_DIR) \
               $(BSW_INC)

# -O1: -O0 blew past 64 KB once Com/PduR/CanIf landed. -O1 still keeps
# the symbols traceable in gdb but trims enough to fit comfortably in
# the H7's 128 KB AXI flash sector. -g3 stays for debug info.
CFLAGS      := $(ARCH_FLAGS) $(DEFS) -O1 -g3 \
               -ffunction-sections -fdata-sections \
               -Wall -Wextra -Wno-unused-parameter \
               $(INC_FLAGS)

ASFLAGS     := $(ARCH_FLAGS) -x assembler-with-cpp

# -nostartfiles: use cmsis-device-h7's Reset_Handler as the entry
# point; -specs=nano.specs pulls in newlib-nano (small libc); -lc
# -lnosys satisfies syscalls (_read/_write/_exit/...) with stubs.
LDFLAGS     := $(ARCH_FLAGS) -T$(LDSCRIPT) \
               -Wl,--gc-sections -Wl,-Map=$(BUILD_DIR)/$(PROJECT).map \
               -nostartfiles -specs=nano.specs -lc -lnosys

# Sources / objects
C_SOURCES   := $(SRC_DIR)/main.c \
               $(SRC_DIR)/Can_Cfg.c \
               $(SRC_DIR)/Can_H7.c \
               $(SRC_DIR)/system_init.c \
               $(SYSTEM_C) \
               $(BSW_C) \
               $(GEN_C)
ASM_SOURCES := $(STARTUP_S)

# Map each source path to a build-dir object. Use just the basename so
# vendor/as sources (reached via `../../`) don't escape build/ and
# pollute hardware/vendor/. All our C basenames are unique today; we'd
# learn fast if a collision ever lands.
C_OBJ       := $(addprefix $(BUILD_DIR)/,$(notdir $(C_SOURCES:.c=.o)))
ASM_OBJ     := $(addprefix $(BUILD_DIR)/,$(notdir $(ASM_SOURCES:.s=.o)))
OBJ         := $(C_OBJ) $(ASM_OBJ)

# vpath lets the pattern rules below find each source by basename.
vpath %.c $(sort $(dir $(C_SOURCES)))
vpath %.s $(sort $(dir $(ASM_SOURCES)))

ELF         := $(BUILD_DIR)/$(PROJECT).elf
BIN         := $(BUILD_DIR)/$(PROJECT).bin
HEX         := $(BUILD_DIR)/$(PROJECT).hex

.PHONY: all clean flash flash-openocd size submodule-check \
        generate generated-check

all: submodule-check generated-check $(ELF) $(BIN) $(HEX)
	@echo ""
	@$(SIZE) $(ELF)

# Sanity check the submodules so the failure mode is "init the
# submodule" rather than a screen of "file not found" gcc errors.
submodule-check:
	@test -f $(STARTUP_S) || { \
	    echo "" >&2; \
	    echo "ERROR: cmsis-device-h7 submodule is not initialized." >&2; \
	    echo "       expected $(STARTUP_S)" >&2; \
	    echo "" >&2; \
	    echo "Run from the repo root:" >&2; \
	    echo "  git submodule update --init \\" >&2; \
	    echo "      hardware/stm32h753zi/third_party/cmsis-device-h7 \\" >&2; \
	    echo "      hardware/stm32h753zi/third_party/CMSIS_5" >&2; \
	    echo "" >&2; \
	    exit 2; \
	}
	@test -d $(CMSIS_CORE) || { \
	    echo "ERROR: CMSIS_5 submodule is not initialized." >&2; \
	    echo "       expected $(CMSIS_CORE)" >&2; \
	    exit 2; \
	}
	@test -f $(BSW_DIR)/communication/Com/Com.c || { \
	    echo "ERROR: vendor/as submodule is not initialized." >&2; \
	    echo "       expected $(BSW_DIR)/communication/Com/Com.c" >&2; \
	    echo "       run: git submodule update --init vendor/as" >&2; \
	    exit 2; \
	}

# The build needs the OpenVinci-emitted *_Cfg.c files in generated/.
# Fail with a helpful pointer rather than a confusing "PduR_Cfg.h not
# found" gcc error.
generated-check:
	@test -f $(GEN_DIR)/Com_Cfg.c || { \
	    echo "" >&2; \
	    echo "ERROR: $(GEN_DIR)/ is empty (or stale)." >&2; \
	    echo "" >&2; \
	    echo "Run (from this directory):" >&2; \
	    echo "  make generate" >&2; \
	    echo "" >&2; \
	    echo "That invokes tools/regenerate.py, which stages" >&2; \
	    echo "examples/com-minimal and runs OpenVinci's generators" >&2; \
	    echo "into $(GEN_DIR)/. Same code path the desktop app uses." >&2; \
	    echo "" >&2; \
	    exit 2; \
	}

# Regenerate Com_Cfg / PduR_Cfg / CanIf_Cfg from examples/com-minimal
# using OpenVinci's own backend (backend/gen/{stage,generate}.py) —
# i.e. the same generator the web/desktop UI calls. See
# `tools/regenerate.py` for the wiring.
generate:
	python3 tools/regenerate.py

$(ELF): $(OBJ)
	@mkdir -p $(@D)
	$(CC) $(OBJ) $(LDFLAGS) -o $@

$(BIN): $(ELF)
	$(OBJCOPY) -O binary $< $@

$(HEX): $(ELF)
	$(OBJCOPY) -O ihex $< $@

$(BUILD_DIR)/%.o: %.c
	@mkdir -p $(@D)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/%.o: %.s
	@mkdir -p $(@D)
	$(CC) $(ASFLAGS) -c $< -o $@

clean:
	rm -rf $(BUILD_DIR)

# Flash with st-link tools (`apt install stlink-tools`). The
# Nucleo-H753ZI shows up as ST-LINK/V2-1 — no `--probe` needed.
flash: $(BIN)
	st-flash --reset write $(BIN) 0x8000000

# Alternative: OpenOCD (`apt install openocd`).
flash-openocd: $(ELF)
	openocd -f interface/stlink.cfg -f target/stm32h7x.cfg \
	    -c "program $(ELF) verify reset exit"

size: $(ELF)
	$(SIZE) $(ELF)
