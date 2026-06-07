/*
 * Can_Cfg.h — config shape for the STM32H753ZI FDCAN backend.
 *
 * Two configs live here:
 *
 *   1. The vendor knobs vendor/as/infras/mcal/Can/Can.c reads:
 *      CAN_NUM_CHANNELS, CAN_USE_CTRL_AC_GLOBAL. These haven't changed
 *      from PROMPT H2.
 *
 *   2. The new H7-backend driver-config table (PROMPT C1). The vendor
 *      MCAL never looks at this — it's a contract between Can_Cfg.c
 *      (hand-written today, generated tomorrow) and Can_H7.c. Putting
 *      the H7-specific config in a separate aggregate keeps the
 *      vendor seam unchanged while letting the backend become fully
 *      table-driven.
 *
 *   Goal of (2): nothing message-specific or layout-specific should
 *   live as a baked-in constant inside Can_H7.c. NBTP register value,
 *   message-RAM region offsets, Rx filters (canid → Hrh), and Tx slot
 *   assignments (Hth → buffer index) all come from this table.
 *
 *   Critical seam (unchanged from H2, re-stated for the new table):
 *     generated/CanIf_Cfg.c: TxPdu.hoh = 0, RxPdu.hoh = 0
 *     Can_H7_Config.rxFilters[0] = { .canid = 0x100, .Hrh = 0 }
 *     Can_H7_Config.txSlots[0]   = { .Hth   = 0,     .bufferIndex = 0 }
 *   Change the table → change the silicon's behaviour; nothing else.
 */
#ifndef CAN_CFG_H
#define CAN_CFG_H

#include "Std_Types.h"
#include "Can_GeneralTypes.h"   /* Can_HwHandleType, Can_IdType */

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------- vendor MCAL knobs (unchanged) ---------------- */

/* Bring CanAc_GlobalInit into Can_Init. Required so FDCAN1 gets its
 * one-shot peripheral setup before the first SetControllerMode. */
#define CAN_USE_CTRL_AC_GLOBAL

/* One controller, one channel: hwInstance 0 == channel 0 == FDCAN1. */
#define CAN_NUM_CHANNELS  1u

/* ---------------- H7 backend driver config (PROMPT C1) ---------- */

/* Pack a Nominal Bit Timing & Prescaler register value (FDCAN_NBTP).
 * Field positions match RM0433 §57.6.2 — keeping the encoding here
 * means Can_Cfg.c stays free of CMSIS bit-position headers and can be
 * emitted directly by a generator.
 *
 * Arguments are the raw register fields, **already minus 1** (M_CAN
 * encodes each as "value - 1"). e.g. for BRP=10 / TSEG1=13 / TSEG2=2
 * / SJW=1, pass (9, 12, 1, 0). */
#define CAN_H7_NBTP(nbrp_m1, ntseg1_m1, ntseg2_m1, nsjw_m1)                \
    (((uint32_t)(nsjw_m1)   << 25) |                                       \
     ((uint32_t)(nbrp_m1)   << 16) |                                       \
     ((uint32_t)(ntseg1_m1) <<  8) |                                       \
     ((uint32_t)(ntseg2_m1) <<  0))


/* One Rx filter entry.
 *
 * Match rule applied per incoming frame in software:
 *   (rx_canid & mask) == (canid & mask) && rx_extended == isExtended
 * The first matching entry wins. On match, the backend hands the
 * frame to CanIf_RxIndication with Mailbox.Hoh = Hrh — same shape the
 * generated CanIf expects.
 *
 * (Why software-side matching? The M_CAN's hardware filter table can
 * do the same job via SIDFC/XIDFC, but routing via a software lookup
 * gives us one place where "which canids does this driver accept"
 * lives — that's the seam we want before we plug a generator into it
 * in PROMPT C2. The hardware filter stays on accept-all-to-FIFO0 for
 * now; we can move the table into MRAM later without changing the
 * upper-layer contract.) */
typedef struct {
    Can_IdType        canid;
    Can_IdType        mask;
    Can_HwHandleType  Hrh;
    uint8_t           isExtended;   /* 0 = 11-bit std, 1 = 29-bit ext */
} Can_H7_RxFilterType;

/* One Tx slot entry. Hth is the logical handle generated CanIf hands
 * to Can_Write; bufferIndex picks the dedicated M_CAN Tx buffer
 * (0..numTxSlots-1) inside the TXBC region. */
typedef struct {
    Can_HwHandleType  Hth;
    uint8_t           bufferIndex;
} Can_H7_TxSlotType;

/* Where each FDCAN message-RAM region lives in the shared SRAMCAN
 * block. All offsets/sizes in 32-bit word units, matching what the
 * RXF0C / TXBC / RXESC / TXESC registers encode. */
typedef struct {
    uint16_t  rxFifo0WordOffset;
    uint8_t   rxFifo0Elements;
    uint8_t   rxFifo0ElemWords;  /* 4 = 8 B data field (Classic CAN)  */
    uint16_t  txBufWordOffset;
    uint8_t   txBufElements;
    uint8_t   txBufElemWords;
} Can_H7_MramLayoutType;

/* The whole H7-backend config for one controller. Single global of
 * this type today (single FDCAN1); growing to an array per channel is
 * a future when FDCAN2 lands. */
typedef struct {
    /* Pre-computed register values. Keeping them as ready-to-write
     * uint32s means the generator's bit-timing math runs once at
     * config time, not on every Init. */
    uint32_t                       nbtp;   /* Nominal Bit Timing & Prescaler */
    uint32_t                       dbtp;   /* Data Bit Timing — 0 if FD off  */

    Can_H7_MramLayoutType          mram;

    const Can_H7_RxFilterType     *rxFilters;
    uint8_t                        numRxFilters;

    const Can_H7_TxSlotType       *txSlots;
    uint8_t                        numTxSlots;
} Can_H7_HwConfigType;

/* Defined in src/Can_Cfg.c. Read-only at run-time. */
extern const Can_H7_HwConfigType Can_H7_Config;

#ifdef __cplusplus
}
#endif

#endif /* CAN_CFG_H */
