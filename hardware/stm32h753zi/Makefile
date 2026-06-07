# Cross-build for STM32H753ZI Nucleo-144 ("hello" over USART3 VCP).
#
# Sources: cmsis-device-h7's gcc startup_stm32h753xx.s +
# system_stm32h7xx.c (default clock init) + our src/main.c.
# Linker: hardware/stm32h753zi/linker/stm32h753xx_flash.ld (we ship
# our own — the upstream cmsis-device-h7 only has gcc linkers for
# dual-core H7s).
#
# This Makefile is intentionally isolated from the repo's top-level
# Makefile — none of `make build` / `make run` / `make desktop-app` /
# `make verify` reference this directory. Run from inside
# hardware/stm32h753zi/:
#
#     make            # → build/stm32h753zi-hello.{elf,bin}
#     make flash      # st-flash write build/stm32h753zi-hello.bin 0x8000000
#     make flash-openocd
#     make clean
#     make size       # arm-none-eabi-size summary

PROJECT     := stm32h753zi-hello

# Cross toolchain — apt: gcc-arm-none-eabi. Override with `make
# CROSS=...` if your toolchain prefix differs (e.g. local builds in
# /opt/gcc-arm/bin/arm-none-eabi-).
CROSS       ?= arm-none-eabi-
CC          := $(CROSS)gcc
OBJCOPY     := $(CROSS)objcopy
SIZE        := $(CROSS)size

# Layout
SRC_DIR     := src
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

# Cortex-M7F (FPU, hard-float ABI to match what cmsis-device-h7's
# startup is compiled for).
ARCH_FLAGS  := -mcpu=cortex-m7 -mthumb \
               -mfpu=fpv5-d16 -mfloat-abi=hard

# Selects the right register map inside cmsis-device-h7's headers
# (stm32h7xx.h dispatches by part-number #define).
DEFS        := -DSTM32H753xx

INC_FLAGS   := -I$(CMSIS_CORE) -I$(DEV_INC)

# -O0 -g3 keeps the symbols readable while we're bringing up the
# board; trim once we land actual functionality.
CFLAGS      := $(ARCH_FLAGS) $(DEFS) -O0 -g3 \
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
C_SOURCES   := $(SRC_DIR)/main.c $(SYSTEM_C)
ASM_SOURCES := $(STARTUP_S)

C_OBJ       := $(C_SOURCES:%.c=$(BUILD_DIR)/%.o)
ASM_OBJ     := $(ASM_SOURCES:%.s=$(BUILD_DIR)/%.o)
OBJ         := $(C_OBJ) $(ASM_OBJ)

ELF         := $(BUILD_DIR)/$(PROJECT).elf
BIN         := $(BUILD_DIR)/$(PROJECT).bin
HEX         := $(BUILD_DIR)/$(PROJECT).hex

.PHONY: all clean flash flash-openocd size submodule-check

all: submodule-check $(ELF) $(BIN) $(HEX)
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
