/*
 * board.h — board-specific helpers for the Nucleo-H753ZI.
 *
 * Kept tiny and hand-written: it's the layer the generated EcuM /
 * Sched / App seam call into when they need to touch *board*-specific
 * pins (UART, LED, button). The generator can't own this because it
 * varies per board (LED on PB0 here vs PC13 on a Bluepill, etc.).
 */
#ifndef OPENVINCI_BOARD_H
#define OPENVINCI_BOARD_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Clock + USART3 (ST-LINK VCP at 115200 8N1). Idempotent — safe to
 * call from EcuM startup before the BSW init chain. */
void board_init(void);

/* Null-terminated string out the VCP. Blocks until the FIFO drains. */
void board_vcp_puts(const char *s);

/* One byte as two hex digits (uppercase), no surrounding decoration. */
void board_vcp_put_hex8(uint8_t v);

#ifdef __cplusplus
}
#endif

#endif /* OPENVINCI_BOARD_H */
