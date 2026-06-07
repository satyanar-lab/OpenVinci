/*
 * STM32H753ZI flash linker script — Nucleo-144 single-core variant.
 *
 * The upstream `cmsis-device-h7/Source/Templates/gcc/linker/` ships
 * scripts only for dual-core H7s (H745/H747/H755/H757); the single-
 * core H753 doesn't have one upstream. This file is a minimal adapt
 * of the H745 CM7 reference (2019 STMicroelectronics, same licence
 * terms) — same section layout, sized for the H753ZI's actual
 * memory map.
 *
 * Memory map (single-core H753ZI, M7 only):
 *   FLASH        2 MB @ 0x08000000
 *   DTCM RAM   128 KB @ 0x20000000  (chosen as primary RAM here)
 *   AXI SRAM   512 KB @ 0x24000000  (free for future use)
 *   ITCM RAM    64 KB @ 0x00000000  (free for future use)
 */

ENTRY(Reset_Handler)

/* Highest address of the user-mode stack (top of DTCM). */
_estack = 0x20020000;

_Min_Heap_Size  = 0x200;  /* 512 B  */
_Min_Stack_Size = 0x400;  /* 1 KB   */

MEMORY
{
  FLASH   (rx)  : ORIGIN = 0x08000000, LENGTH = 2048K
  RAM     (xrw) : ORIGIN = 0x20000000, LENGTH = 128K
  ITCMRAM (xrw) : ORIGIN = 0x00000000, LENGTH = 64K
  AXISRAM (xrw) : ORIGIN = 0x24000000, LENGTH = 512K
}

SECTIONS
{
  .isr_vector :
  {
    . = ALIGN(4);
    KEEP(*(.isr_vector))
    . = ALIGN(4);
  } >FLASH

  .text :
  {
    . = ALIGN(4);
    *(.text)
    *(.text*)
    *(.glue_7)
    *(.glue_7t)
    *(.eh_frame)

    KEEP (*(.init))
    KEEP (*(.fini))

    . = ALIGN(4);
    _etext = .;
  } >FLASH

  .rodata :
  {
    . = ALIGN(4);
    *(.rodata)
    *(.rodata*)
    . = ALIGN(4);
  } >FLASH

  .ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } >FLASH
  .ARM :
  {
    __exidx_start = .;
    *(.ARM.exidx*)
    __exidx_end = .;
  } >FLASH

  .preinit_array :
  {
    PROVIDE_HIDDEN (__preinit_array_start = .);
    KEEP (*(.preinit_array*))
    PROVIDE_HIDDEN (__preinit_array_end = .);
  } >FLASH
  .init_array :
  {
    PROVIDE_HIDDEN (__init_array_start = .);
    KEEP (*(SORT(.init_array.*)))
    KEEP (*(.init_array*))
    PROVIDE_HIDDEN (__init_array_end = .);
  } >FLASH
  .fini_array :
  {
    PROVIDE_HIDDEN (__fini_array_start = .);
    KEEP (*(SORT(.fini_array.*)))
    KEEP (*(.fini_array*))
    PROVIDE_HIDDEN (__fini_array_end = .);
  } >FLASH

  _sidata = LOADADDR(.data);

  .data :
  {
    . = ALIGN(4);
    _sdata = .;
    *(.data)
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } >RAM AT> FLASH

  . = ALIGN(4);
  .bss :
  {
    _sbss = .;
    __bss_start__ = _sbss;
    *(.bss)
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
    __bss_end__ = _ebss;
  } >RAM

  ._user_heap_stack :
  {
    . = ALIGN(8);
    PROVIDE ( end = . );
    PROVIDE ( _end = . );
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  } >RAM

  /DISCARD/ :
  {
    libc.a ( * )
    libm.a ( * )
    libgcc.a ( * )
  }

  .ARM.attributes 0 : { *(.ARM.attributes) }
}
