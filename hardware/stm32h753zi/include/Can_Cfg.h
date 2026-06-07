/*
 * Hand-written Can_Cfg.h for the STM32H753ZI port.
 *
 * vendor/as has no upstream `Can` JSON generator (see
 * docs/AUTOAS_NOTES.md §1.2) — Can_Cfg.{h,c} are always hand-authored
 * for the target. We declare a single controller (channel 0, FDCAN1)
 * to match what `examples/com-minimal` references via
 * CanIf_TxPdus[].ControllerId = 0 in the generated `CanIf_Cfg.c`.
 *
 * Knobs `vendor/as/infras/mcal/Can/Can.c` reads:
 *   USE_PORT                            — undefined: vendor MCAL goes
 *                                         through CanAc_SetupPinMode /
 *                                         CanAc_WritePin instead of the
 *                                         AUTOSAR Port driver. Our H7
 *                                         backend (`src/Can_H7.c`) does
 *                                         GPIO config directly.
 *   CAN_USE_CTRL_AC_GLOBAL              — defined: Can_Init calls
 *                                         CanAc_GlobalInit so we can
 *                                         clock and pre-configure
 *                                         FDCAN1 once.
 *   CAN_USE_CTRL_AC_CONTEXT_TYPE        — undefined.
 *   CAN_USE_CTRL_AC_CONFIG_TYPE         — undefined.
 */
#ifndef CAN_CFG_H
#define CAN_CFG_H

#include "Std_Types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Bring CanAc_GlobalInit into Can_Init. Required so FDCAN1 gets its
 * one-shot peripheral setup before the first SetControllerMode. */
#define CAN_USE_CTRL_AC_GLOBAL

/* One controller, one channel: hwInstance 0 == channel 0 == FDCAN1.
 *
 * THIS IS THE CRITICAL SEAM the prompt asks us to document:
 *
 *   generated/CanIf_Cfg.c:
 *     CanIf_TxPdus[]   = { { .canid = 0x100, .hoh = 0, .ControllerId = 0 } }
 *     CanIf_RxPdus_CAN0[] = { { .canid = 0x101, .hoh = 0 } }
 *
 *   hardware/stm32h753zi/src/Can_Cfg.c:
 *     numOfChannels = 1
 *     hwIns2ChlMap  = { 0 }              // FDCAN1 → channel 0
 *
 *   hardware/stm32h753zi/src/Can_H7.c:
 *     channel 0 == FDCAN1 instance.
 *     Hth = 0  → FDCAN1 Tx Buffer #0   (TXBC.TBSA + 0 * elemSize)
 *     Hrh = 0  → FDCAN1 Rx FIFO 0      (RXF0C.F0SA, read via RXF0S/RXF0A)
 *
 *   Filtering on Rx: the generated CanIf does its own canid lookup
 *   from CanIf_RxIndication's Mailbox.CanId. So FDCAN1 is configured
 *   in "accept all" mode (GFC global filter falls through to FIFO 0
 *   for non-matching frames) — no per-id hardware filters are wired
 *   up here. Matches how the simulator broker test treats hoh=0.
 */
#define CAN_NUM_CHANNELS  1u

#ifdef __cplusplus
}
#endif

#endif /* CAN_CFG_H */
