/*
 * FDCAN1 backend for STM32H753ZI — implements the CanAc_* contract
 * from vendor/as `infras/mcal/Can/Can.c`, plus the BSP-side
 * `Can_Write` and the `Can_MainFunction_*` pumps.
 *
 * PROMPT C1: every message-specific or layout-specific constant that
 * used to live as a `#define` in this file now flows in from a
 * driver-config table (`Can_H7_Config`, defined in src/Can_Cfg.c via
 * the shape declared in include/Can_Cfg.h). CanAc_Init / Can_Write /
 * Can_MainFunction_Read all iterate that table. The .c file no longer
 * encodes which CAN ids are accepted, which Tx buffer Hth=N points
 * at, the NBTP register value, or the MRAM region offsets — change
 * the table → change the silicon's behaviour; nothing else.
 *
 * Datasheet references: STM32H7 RM0433 §57 (FDCAN, "M_CAN block").
 *
 * Scope (unchanged from PROMPT H3):
 *   - Classic CAN frames only (no FD; DLC ≤ 8).
 *   - FDCAN1 in INTERNAL LOOPBACK — bare Nucleo-H753ZI, no
 *     transceiver. The looped frame still goes the long way:
 *     Can_Write → Tx Buffer → M_CAN → Rx FIFO 0 →
 *     Can_MainFunction_Read → CanIf_RxIndication.
 */

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "stm32h753xx.h"

#include "Std_Types.h"
#include "Can.h"
#include "Can_Priv.h"
#include "Can_Cfg.h"
#include "CanIf_Can.h"
#include "CanIf.h"

extern Can_ConfigType Can_Config;

/* CMSIS for H7 doesn't define an XTD-bit macro for the message-RAM
 * element layout (it's a software convention, not an MMIO field).
 * Spell it out so the Rx parser below can discriminate std/ext IDs. */
#define FDCAN_ELEMENT_XTD (1u << 30)

/* Bounded so a stack-allocated array can hold per-slot Tx state with
 * no malloc. Bigger than anything h7-loopback or any plausible single-
 * channel config needs; raise (and re-verify the build) if a future
 * config table runs into it. */
#define CAN_H7_MAX_TX_SLOTS 8u

/* ============================================================ MEM RAM
 *
 * STM32H7 shares 2.5 KB of message RAM between FDCAN1 and FDCAN2 at
 * SRAMCAN_BASE (0x4000AC00). Where in there each region sits is read
 * from Can_H7_Config.mram on init — no offsets baked in here. */

#define FDCAN1_MRAM_BASE   ((volatile uint32_t *)SRAMCAN_BASE)

static inline volatile uint32_t *rx_fifo0_elem(uint32_t idx)
{
    const Can_H7_MramLayoutType *m = &Can_H7_Config.mram;
    return &FDCAN1_MRAM_BASE[m->rxFifo0WordOffset
                             + idx * m->rxFifo0ElemWords];
}

static inline volatile uint32_t *tx_buf_elem(uint32_t idx)
{
    const Can_H7_MramLayoutType *m = &Can_H7_Config.mram;
    return &FDCAN1_MRAM_BASE[m->txBufWordOffset
                             + idx * m->txBufElemWords];
}

/* ============================================== Per-slot Tx state
 *
 * Mutable side-table: indexed by the same slot index as
 * Can_H7_Config.txSlots[i]. Each entry remembers the swPduHandle the
 * upper layer handed us in Can_Write, so MainFunction_WriteChannel
 * can hand the right id back via CanIf_TxConfirmation when the M_CAN
 * reports TXBTO for that buffer. */
typedef struct {
    PduIdType pendingHandle;
    uint8_t   pending;
} Can_H7_TxRuntimeType;

static Can_H7_TxRuntimeType s_tx_runtime[CAN_H7_MAX_TX_SLOTS];

/* Find the txSlots[] index whose .Hth matches the upper-layer handle.
 * Returns numTxSlots on miss (so a > check is enough to reject). */
static uint8_t find_tx_slot(Can_HwHandleType Hth)
{
    const Can_H7_HwConfigType *c = &Can_H7_Config;
    for (uint8_t i = 0u; i < c->numTxSlots; i++) {
        if (c->txSlots[i].Hth == Hth) {
            return i;
        }
    }
    return c->numTxSlots;
}

/* ========================================================== INIT-MODE */

static void fdcan_enter_init(void)
{
    /* Request init mode and wait for the controller to acknowledge.
     * Per RM0433 §57.4.5, INIT goes high a few cycles after the
     * request; the spin-wait is bounded by the configured CAN bit
     * time, so we don't add an explicit timeout here. */
    FDCAN1->CCCR |= FDCAN_CCCR_INIT;
    while ((FDCAN1->CCCR & FDCAN_CCCR_INIT) == 0u) { }
    FDCAN1->CCCR |= FDCAN_CCCR_CCE;
}

static void fdcan_leave_init(void)
{
    FDCAN1->CCCR &= ~(FDCAN_CCCR_CCE | FDCAN_CCCR_INIT);
    while ((FDCAN1->CCCR & FDCAN_CCCR_INIT) != 0u) { }
}

/* ====================================================== BIT-TIMING */

static void fdcan_program_bit_timing(void)
{
    /* Pre-encoded by Can_Cfg.c via CAN_H7_NBTP(...). No field math
     * in the .c. */
    FDCAN1->NBTP = Can_H7_Config.nbtp;
    /* DBTP only matters when CCCR.FDOE/CCCR.BRSE are set; this build
     * keeps them at 0, but write it anyway so a future FD config just
     * has to flip one .dbtp field in the table. */
    FDCAN1->DBTP = Can_H7_Config.dbtp;
}

/* ====================================================== MRAM LAYOUT */

static void fdcan_configure_mram(void)
{
    const Can_H7_MramLayoutType *m = &Can_H7_Config.mram;

    /* Hardware filter tables stay empty — Rx canid → Hrh routing
     * happens in software against Can_H7_Config.rxFilters[] (see
     * Can_Cfg.h for the rationale). */
    FDCAN1->SIDFC = 0u;
    FDCAN1->XIDFC = 0u;

    /* Rx FIFO 0: blocking mode (F0OM = 0), watermark off. */
    FDCAN1->RXF0C = ((uint32_t)m->rxFifo0WordOffset << FDCAN_RXF0C_F0SA_Pos)
                  | ((uint32_t)m->rxFifo0Elements   << FDCAN_RXF0C_F0S_Pos);

    /* Rx FIFO 1 + Rx Buffer + Tx Event FIFO unused. */
    FDCAN1->RXF1C = 0u;
    FDCAN1->RXBC  = 0u;
    FDCAN1->TXEFC = 0u;

    /* Tx: numTxSlots dedicated buffers (no Tx FIFO/Queue). */
    FDCAN1->TXBC = ((uint32_t)m->txBufWordOffset << FDCAN_TXBC_TBSA_Pos)
                 | ((uint32_t)m->txBufElements   << FDCAN_TXBC_NDTB_Pos);

    /* Element data-field size = 8 bytes for both Rx and Tx → Classic
     * CAN only. (For FD: bump to 7 = 64 B and re-jig elemWords in the
     * MRAM layout.) */
    FDCAN1->RXESC = (0u << FDCAN_RXESC_F0DS_Pos)
                  | (0u << FDCAN_RXESC_F1DS_Pos)
                  | (0u << FDCAN_RXESC_RBDS_Pos);
    FDCAN1->TXESC = (0u << FDCAN_TXESC_TBDS_Pos);

    /* Global filter: route non-matching std/ext frames to FIFO 0 so
     * the software rxFilters table sees them; drop remote-frame
     * requests (we don't model RTR). */
    FDCAN1->GFC = (0u << FDCAN_GFC_ANFS_Pos)   /* std non-match → F0 */
                  | (0u << FDCAN_GFC_ANFE_Pos)   /* ext non-match → F0 */
                  | FDCAN_GFC_RRFS               /* drop remote std    */
                  | FDCAN_GFC_RRFE;              /* drop remote ext    */
}

/* ===================================================== TEST / LOOPBACK */

static void fdcan_enable_internal_loopback(void)
{
    /* Internal Loopback per RM0433 §57.4.5:
     *   CCCR.TEST = 1, CCCR.MON = 1, TEST.LBCK = 1
     * MON=1 disconnects the Tx output from the bus driver pin; LBCK=1
     * routes the internal Tx back to the internal Rx. */
    FDCAN1->CCCR |= FDCAN_CCCR_TEST | FDCAN_CCCR_MON;
    FDCAN1->TEST  = FDCAN_TEST_LBCK;
}

/* ============================================================ PIN MUX
 *
 * Nucleo-H753ZI maps FDCAN1 to PD0 (RX) / PD1 (TX) on connector CN9
 * (alternate function 9). For pure internal loopback the pins are
 * inert, but configuring them anyway mirrors the real-board setup
 * we'll use once a transceiver lands.
 */
static void fdcan_configure_pins(void)
{
    RCC->AHB4ENR |= RCC_AHB4ENR_GPIODEN;

    GPIOD->MODER &= ~(GPIO_MODER_MODE0_Msk | GPIO_MODER_MODE1_Msk);
    GPIOD->MODER |=  (2u << GPIO_MODER_MODE0_Pos)
                  |  (2u << GPIO_MODER_MODE1_Pos);  /* AF mode */

    GPIOD->AFR[0] &= ~(GPIO_AFRL_AFSEL0_Msk | GPIO_AFRL_AFSEL1_Msk);
    GPIOD->AFR[0] |=  (9u << GPIO_AFRL_AFSEL0_Pos)
                  |   (9u << GPIO_AFRL_AFSEL1_Pos); /* AF9 = FDCAN1 */

    GPIOD->OTYPER  &= ~(GPIO_OTYPER_OT0 | GPIO_OTYPER_OT1);
    GPIOD->OSPEEDR |=  (3u << GPIO_OSPEEDR_OSPEED0_Pos)
                   |   (3u << GPIO_OSPEEDR_OSPEED1_Pos);
    GPIOD->PUPDR   &= ~(GPIO_PUPDR_PUPD0_Msk | GPIO_PUPDR_PUPD1_Msk);
}

/* ============================================== CanAc_* — vendor MCAL */

Std_ReturnType CanAc_GlobalInit(const Can_ConfigType *Config)
{
    (void)Config;

    /* Clock the peripheral. RCC->APB1HENR.FDCAN1EN (bit 8). */
    RCC->APB1HENR |= RCC_APB1HENR_FDCANEN;
    (void)RCC->APB1HENR;     /* RCC enable → access sync */

    return E_OK;
}

Std_ReturnType CanAc_GlobalDeInit(const Can_ConfigType *Config)
{
    (void)Config;
    RCC->APB1HENR &= ~RCC_APB1HENR_FDCANEN;
    return E_OK;
}

Std_ReturnType CanAc_Init(uint8_t Controller, const Can_ChannelConfigType *config)
{
    if (Controller != 0u) {
        return E_NOT_OK;        /* only FDCAN1 in this build */
    }
    (void)config;

    /* A config that claims more Tx slots than our compile-time max can
     * hold per-slot runtime state for. Caught at init so the failure
     * isn't a confusing buffer-overrun later. */
    if (Can_H7_Config.numTxSlots > CAN_H7_MAX_TX_SLOTS) {
        return E_NOT_OK;
    }

    /* Reset per-slot Tx runtime state. */
    for (uint8_t i = 0u; i < CAN_H7_MAX_TX_SLOTS; i++) {
        s_tx_runtime[i].pendingHandle = 0u;
        s_tx_runtime[i].pending       = 0u;
    }

    fdcan_configure_pins();
    fdcan_enter_init();
    fdcan_program_bit_timing();
    fdcan_configure_mram();
    fdcan_enable_internal_loopback();
    fdcan_leave_init();

    return E_OK;
}

Std_ReturnType CanAc_DeInit(uint8_t Controller, const Can_ChannelConfigType *config)
{
    if (Controller != 0u) {
        return E_NOT_OK;
    }
    (void)config;
    fdcan_enter_init();
    return E_OK;
}

Std_ReturnType CanAc_SetSleepMode(uint8_t Controller,
                                  const Can_ChannelConfigType *config)
{
    return CanAc_DeInit(Controller, config);
}

Std_ReturnType CanAc_SetupPinMode(const Can_CtrlPinType *pin)
{
    (void)pin;
    return E_OK;
}

Std_ReturnType CanAc_WritePin(const Can_CtrlPinType *pin, uint8_t value)
{
    (void)pin;
    (void)value;
    return E_OK;
}

/* ========================================== Can_Write — BSP entrypoint
 *
 * Hth is the logical handle generated CanIf hands us; we look it up in
 * Can_H7_Config.txSlots[] to find the dedicated buffer it maps to.
 */
Std_ReturnType Can_Write(Can_HwHandleType Hth, const Can_PduType *PduInfo)
{
    if (PduInfo == NULL || PduInfo->sdu == NULL) {
        return E_NOT_OK;
    }
    /* Refuse FD-sized payloads — this build is Classic-CAN only. */
    uint8_t dlc = PduInfo->length;
    if (dlc > 8u) {
        return E_NOT_OK;
    }

    const uint8_t slot_idx = find_tx_slot(Hth);
    if (slot_idx >= Can_H7_Config.numTxSlots) {
        return E_NOT_OK;        /* Hth not in table */
    }
    const uint8_t buf_idx = Can_H7_Config.txSlots[slot_idx].bufferIndex;
    const uint32_t buf_bit = (1u << buf_idx);

    /* If the previous TXBAR for this buffer hasn't drained yet, refuse
     * — CanIf will buffer via its pool and retry. */
    if ((FDCAN1->TXBRP & buf_bit) != 0u) {
        return CAN_BUSY;
    }

    volatile uint32_t *e = tx_buf_elem(buf_idx);

    /* T0: id field. 29-bit ids land at bits 0..28 with XTD=1; 11-bit
     * ids land at bits 18..28 with XTD=0. The table's isExtended flag
     * doesn't apply here (it's an Rx-filter field) — we pick the
     * encoding based on the id's magnitude, which is what the AUTOSAR
     * Can_IdType convention does (top bit = extended). */
    uint32_t t0 = 0u;
    if ((PduInfo->id & 0x80000000u) != 0u) {
        const uint32_t id29 = PduInfo->id & 0x1FFFFFFFu;
        t0 = id29 | FDCAN_ELEMENT_XTD;
    } else {
        t0 = ((PduInfo->id & 0x7FFu) << 18);
    }
    e[0] = t0;

    /* T1: DLC = dlc, FDF = 0 (classic), BRS = 0, EFC = 0. */
    e[1] = ((uint32_t)dlc & 0x0Fu) << 16;

    /* T2 / T3: pack up to 8 bytes little-endian. */
    uint32_t w2 = 0u;
    uint32_t w3 = 0u;
    for (uint8_t i = 0u; i < dlc; i++) {
        uint8_t b = PduInfo->sdu[i];
        if (i < 4u) {
            w2 |= ((uint32_t)b) << (i * 8u);
        } else {
            w3 |= ((uint32_t)b) << ((i - 4u) * 8u);
        }
    }
    e[2] = w2;
    e[3] = w3;

    /* Stash the swPduHandle so we hand the same id back via
     * CanIf_TxConfirmation when the M_CAN reports TXBTO for this
     * buffer. */
    s_tx_runtime[slot_idx].pendingHandle = PduInfo->swPduHandle;
    s_tx_runtime[slot_idx].pending       = 1u;

    /* Request transmission of this buffer. */
    FDCAN1->TXBAR = buf_bit;

    return E_OK;
}

/* ================================================== MainFunction pump
 *
 * Write side: iterate the txSlots table. For each slot whose TXBTO bit
 * is set, W1C-clear it and call CanIf_TxConfirmation with the
 * swPduHandle stashed at Can_Write time.
 *
 * Read side: drain FIFO 0; for each frame, walk the rxFilters table
 * to find the matching canid → Hrh, then hand the frame up.
 */
void Can_MainFunction_WriteChannel(uint8_t Channel)
{
    if (Channel != 0u) {
        return;
    }

    const Can_H7_HwConfigType *c = &Can_H7_Config;
    for (uint8_t i = 0u; i < c->numTxSlots; i++) {
        const uint8_t buf_idx = c->txSlots[i].bufferIndex;
        const uint32_t bit = (1u << buf_idx);
        if ((FDCAN1->TXBTO & bit) == 0u) {
            continue;
        }
        FDCAN1->TXBTO = bit;       /* W1C */

        if (s_tx_runtime[i].pending != 0u) {
            const PduIdType h = s_tx_runtime[i].pendingHandle;
            s_tx_runtime[i].pending = 0u;
            CanIf_TxConfirmation(h);
        }
    }
}

void Can_MainFunction_Write(void)
{
    Can_MainFunction_WriteChannel(0u);
}

/* Walk rxFilters[] for the first entry whose (canid, mask, isExtended)
 * accepts `rx_canid`. Returns numRxFilters on miss. */
static uint8_t match_rx_filter(uint32_t rx_canid, uint8_t rx_extended)
{
    const Can_H7_HwConfigType *c = &Can_H7_Config;
    for (uint8_t i = 0u; i < c->numRxFilters; i++) {
        const Can_H7_RxFilterType *f = &c->rxFilters[i];
        if (f->isExtended != rx_extended) {
            continue;
        }
        if ((rx_canid & f->mask) == (f->canid & f->mask)) {
            return i;
        }
    }
    return c->numRxFilters;
}

void Can_MainFunction_ReadChannel(uint8_t Channel)
{
    if (Channel != 0u) {
        return;
    }

    /* Drain whatever FIFO 0 holds in this tick. */
    while ((FDCAN1->RXF0S & FDCAN_RXF0S_F0FL_Msk) != 0u) {
        const uint32_t get_idx =
            (FDCAN1->RXF0S & FDCAN_RXF0S_F0GI_Msk) >> FDCAN_RXF0S_F0GI_Pos;
        const volatile uint32_t *e = rx_fifo0_elem(get_idx);

        const uint32_t r0 = e[0];
        const uint32_t r1 = e[1];

        const uint8_t dlc_n = (uint8_t)((r1 >> 16) & 0x0Fu);
        const uint8_t dlc   = (dlc_n > 8u) ? 8u : dlc_n;
        const uint8_t  ext  = ((r0 & FDCAN_ELEMENT_XTD) != 0u) ? 1u : 0u;
        const uint32_t canid = (ext != 0u)
                             ? (r0 & 0x1FFFFFFFu)
                             : ((r0 >> 18) & 0x7FFu);

        const uint8_t filter_idx = match_rx_filter(canid, ext);
        if (filter_idx < Can_H7_Config.numRxFilters) {
            uint8_t payload[8];
            const uint32_t w2 = e[2];
            const uint32_t w3 = e[3];
            for (uint8_t i = 0u; i < 8u; i++) {
                payload[i] = (i < 4u)
                           ? (uint8_t)(w2 >> (i * 8u))
                           : (uint8_t)(w3 >> ((i - 4u) * 8u));
            }

            Can_HwType  mailbox;
            PduInfoType info;
            mailbox.CanId        = canid;
            mailbox.ControllerId = 0u;
            mailbox.Hoh          = Can_H7_Config.rxFilters[filter_idx].Hrh;
            info.SduLength       = dlc;
            info.SduDataPtr      = payload;
            info.MetaDataPtr     = (uint8_t *)&mailbox;
            CanIf_RxIndication(&mailbox, &info);
        }
        /* No-match: silently drop. The GFC accept-all + software match
         * design means we may see ids no upper layer cares about; the
         * generated CanIf wouldn't route them anyway. */

        FDCAN1->RXF0A = get_idx;       /* increments FIFO get-index */
    }
}

void Can_MainFunction_Read(void)
{
    Can_MainFunction_ReadChannel(0u);
}

/* The MCAL header declares these BusOff / WakeUp / Mode pumps for
 * completeness; we have no interrupt-driven state here yet, but the
 * symbols still have to resolve at link time. */
void Can_MainFunction_BusOff(void) { }
void Can_MainFunction_WakeUp(void) { }
void Can_MainFunction_Mode(void)   { }
