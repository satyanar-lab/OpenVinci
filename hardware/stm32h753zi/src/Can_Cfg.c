/*
 * Can_Cfg.c — config tables for STM32H753ZI FDCAN1.
 *
 * Two configs live here:
 *
 *   - Can_Config (vendor): what vendor/as Can.c dereferences through
 *     CAN_CONFIG. Same shape as PROMPT H2 (one channel, FDCAN1).
 *
 *   - Can_H7_Config (new in C1): the driver-config table our backend
 *     (Can_H7.c) reads on init and on every Rx/Tx. Encodes the NBTP
 *     register value, the FDCAN message-RAM layout, the Rx filter
 *     list (canid → Hrh), and the Tx slot list (Hth → buffer index).
 *
 *   Today this file is hand-written and the tables describe the
 *   `examples/h7-loopback` setup byte-for-byte the same as the
 *   PROMPT H3 hardcoded constants did. PROMPT C2 will replace this
 *   file with an OpenVinci-emitted version sourced from the same
 *   project tree the upper-layer *_Cfg.c files come from.
 */

#include "Can.h"
#include "Can_Priv.h"
#include "Can_Cfg.h"

/* ============================================================ vendor
 * The Can_ConfigType vendor/as Can.c dereferences via CAN_CONFIG. */

static Can_ChannelContextType s_can0_context;

static const Can_ChannelConfigType s_can0_cfg = {
    .context = &s_can0_context,
#ifndef USE_PORT
    .CtrlPins = NULL,
    .numOfCtrlPins = 0,
    .TrcvPinSTB = 0,
#endif
    .baudrate = 500000u,
    .samplePoint = 88u,     /* uint8_t "unit 1 %", vendor Can_Priv.h:58.
                             * Precise 87.5 % is realised by the NBTP
                             * register value below (TSEG1=13, TSEG2=2). */
    .hwInstanceId = 0u,
    .NormalValueOfTrcvPinSTB = 0u,
};

static const Can_ChannelConfigType s_channel_configs[1] = { s_can0_cfg };
static const uint8_t s_hw_to_channel[1] = { 0u };

Can_ConfigType Can_Config = {
    .channelConfigs    = s_channel_configs,
    .hwIns2ChlMap      = s_hw_to_channel,
    .numOfChannels     = CAN_NUM_CHANNELS,
    .sizeOfhwIns2ChlMap = (uint8_t)(sizeof(s_hw_to_channel) /
                                    sizeof(s_hw_to_channel[0])),
};

/* ====================================================== H7 backend
 *
 * Encode the h7-loopback setup the H3 prompt verified on real silicon.
 * Behaviour is identical to the H3 commit; the only change is that the
 * numbers now flow through a struct instead of being baked into
 * Can_H7.c with `#define`s. */

/* Rx filters: one entry per accepted CAN id. The h7-loopback example
 * ships exactly one Rx PDU (canid 0x100, Hrh 0) — the same id the
 * generated CanIf_Cfg.c lists in CanIf_RxPdus_CAN0[0]. */
static const Can_H7_RxFilterType s_rx_filters[] = {
    {
        .canid      = 0x100u,
        .mask       = 0x7FFu,   /* exact match on 11-bit std id */
        .Hrh        = 0u,       /* matches generated CanIf RxPdu.hoh */
        .isExtended = 0u,
    },
};

/* Tx slots: Hth → dedicated Tx buffer. h7-loopback's only TxPdu is
 * (canid 0x100, Hth 0); we map it to buffer 0. */
static const Can_H7_TxSlotType s_tx_slots[] = {
    {
        .Hth         = 0u,
        .bufferIndex = 0u,
    },
};

const Can_H7_HwConfigType Can_H7_Config = {
    /* 500 kbit/s nominal @ 80 MHz FDCAN kernel clock (PLL2Q in
     * system_init.c):
     *   tq    = 80 MHz / BRP = 80 MHz / 10 = 8 MHz   → 125 ns
     *   bit   = (1 + TSEG1 + TSEG2) × tq = (1 + 13 + 2) × 125 ns = 2 µs
     *   rate  = 500 kbit/s
     *   smp   = (1 + TSEG1) / total = 14/16 = 87.5 % */
    .nbtp = CAN_H7_NBTP(/* nbrp-1   */ 9u,
                        /* ntseg1-1 */ 12u,
                        /* ntseg2-1 */ 1u,
                        /* nsjw-1   */ 0u),
    .dbtp = 0u,    /* FD off in this build */

    /* MRAM layout — same as H3:
     *   Rx FIFO 0 @ word 0 (3 elements × 4 words)
     *   Tx Buffer @ word 12 (1 element × 4 words)
     * 16 words total = 64 B used out of FDCAN1's 2.5 KB share. */
    .mram = {
        .rxFifo0WordOffset = 0u,
        .rxFifo0Elements   = 3u,
        .rxFifo0ElemWords  = 4u,
        .txBufWordOffset   = 12u,
        .txBufElements     = 1u,
        .txBufElemWords    = 4u,
    },

    .rxFilters    = s_rx_filters,
    .numRxFilters = (uint8_t)(sizeof(s_rx_filters) / sizeof(s_rx_filters[0])),

    .txSlots      = s_tx_slots,
    .numTxSlots   = (uint8_t)(sizeof(s_tx_slots) / sizeof(s_tx_slots[0])),
};
