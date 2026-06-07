/*
 * FDCAN1 backend for STM32H753ZI — implements the CanAc_* contract
 * that vendor/as `infras/mcal/Can/Can.c` calls down to, plus the
 * BSP-side `Can_Write` and the `Can_MainFunction_*` pump entrypoints
 * that the same MCAL implementation expects.
 *
 * Datasheet references: STM32H7 RM0433 §57 (FDCAN, "M_CAN block").
 *
 * Scope (PROMPT H2):
 *   - Classic CAN frames only (no FD frames; DLC ≤ 8).
 *   - FDCAN1 in INTERNAL LOOPBACK (TEST.LBCK = 1 + CCCR.MON = 1).
 *     Messages stay inside the M_CAN core; no bus drivers required,
 *     so the bare Nucleo-H753ZI (no on-board CAN transceiver) is
 *     enough to prove the OpenVinci-emitted Com → CanIf → driver →
 *     CanIf_RxIndication → Com path round-trips on real silicon.
 *   - 500 kbit/s nominal bit-rate (87.5 % sample point) at an 80 MHz
 *     FDCAN kernel clock the matching `system_init.c` sets up via
 *     PLL2Q.
 *
 * Critical seam (also restated in Can_Cfg.h next to numOfChannels):
 *   generated CanIf:    TxPdu.hoh = 0,  RxPdu.hoh = 0
 *   our Can_Cfg.c:      channel 0 == hwInstanceId 0
 *   THIS FILE:          Hth = 0  → FDCAN1 Tx Buffer #0
 *                       Hrh = 0  → FDCAN1 Rx FIFO 0
 *   On Rx, we deliver Mailbox.Hoh = 0 to CanIf_RxIndication so the
 *   generated CanIf can route by canid the same way the L2 functional
 *   tests already prove on the host simulator.
 */

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "stm32h753xx.h"

#include "Std_Types.h"
#include "Can.h"
#include "Can_Priv.h"
#include "CanIf_Can.h"
#include "CanIf.h"

extern Can_ConfigType Can_Config;

/* CMSIS for H7 doesn't define an XTD-bit macro for the message-RAM
 * element layout (it's a software convention, not an MMIO field).
 * Spell it out so the Rx parser below can discriminate std/ext IDs. */
#define FDCAN_ELEMENT_XTD (1u << 30)

/* ============================================================ MEM RAM
 *
 * STM32H7 shares 2.5 KB of message RAM between FDCAN1 and FDCAN2 at
 * SRAMCAN_BASE (0x4000AC00). We place FDCAN1's element regions at
 * the bottom of that block. All offsets and sizes are in *word*
 * units (4 bytes), per the FDCAN register encoding.
 *
 * Layout (no filters; accept-all into Rx FIFO 0):
 *
 *   word 0  ┐
 *           │  Rx FIFO 0 — 3 elements × 4 words (header 2w + 8 bytes data)
 *   word 11 ┘
 *   word 12 ┐  Tx Buffer — 1 dedicated buffer × 4 words
 *   word 15 ┘
 *
 * That's 16 words = 64 B used. Plenty of headroom for FDCAN2 or for
 * later expansion into FD-sized payloads.
 */

#define FDCAN1_MRAM_BASE   ((volatile uint32_t *)SRAMCAN_BASE)

#define RX_FIFO0_WOFFSET   0u   /* word index inside the shared MRAM   */
#define RX_FIFO0_NELEM     3u
#define RX_FIFO0_ELEMSIZE  4u   /* 2 header words + 2 data words (8 B) */

#define TX_BUF_WOFFSET     (RX_FIFO0_WOFFSET + RX_FIFO0_NELEM * RX_FIFO0_ELEMSIZE)
#define TX_BUF_NELEM       1u
#define TX_BUF_ELEMSIZE    4u

/* Helpers to address an element word-array inside the shared MRAM. */
static inline volatile uint32_t *rx_fifo0_elem(uint32_t idx)
{
    return &FDCAN1_MRAM_BASE[RX_FIFO0_WOFFSET + idx * RX_FIFO0_ELEMSIZE];
}

static inline volatile uint32_t *tx_buf_elem(uint32_t idx)
{
    return &FDCAN1_MRAM_BASE[TX_BUF_WOFFSET + idx * TX_BUF_ELEMSIZE];
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
    /* Enable configuration-change writes. */
    FDCAN1->CCCR |= FDCAN_CCCR_CCE;
}

static void fdcan_leave_init(void)
{
    FDCAN1->CCCR &= ~(FDCAN_CCCR_CCE | FDCAN_CCCR_INIT);
    while ((FDCAN1->CCCR & FDCAN_CCCR_INIT) != 0u) { }
}

/* ====================================================== BIT-TIMING */

/* 500 kbit/s nominal @ 80 MHz FDCAN kernel clock (set up by
 * system_init.c via PLL2Q):
 *
 *   tq      = 1 / (kernel_clk / BRP) = 1 / (80 MHz / 10) = 125 ns
 *   bit_t   = (1 + TSEG1 + TSEG2) × tq = (1 + 13 + 2) × 125 ns = 2 μs
 *   rate    = 500 kbit/s
 *   sample  = (1 + TSEG1) / total = 14/16 = 87.5 %
 */
#define NBTP_NBRP     (10u - 1u)
#define NBTP_NTSEG1   (13u - 1u)
#define NBTP_NTSEG2   (2u  - 1u)
#define NBTP_NSJW     (1u  - 1u)

static void fdcan_program_bit_timing(void)
{
    FDCAN1->NBTP = ((uint32_t)NBTP_NSJW   << FDCAN_NBTP_NSJW_Pos)
                 | ((uint32_t)NBTP_NBRP   << FDCAN_NBTP_NBRP_Pos)
                 | ((uint32_t)NBTP_NTSEG1 << FDCAN_NBTP_NTSEG1_Pos)
                 | ((uint32_t)NBTP_NTSEG2 << FDCAN_NBTP_NTSEG2_Pos);
}

/* ====================================================== MRAM LAYOUT */

static void fdcan_configure_mram(void)
{
    /* No standard / extended ID filters: accept-all routes to FIFO 0
     * via RXGFC.ANFS = 0 below. */
    FDCAN1->SIDFC = 0u;
    FDCAN1->XIDFC = 0u;

    /* Rx FIFO 0: blocking mode (F0OM = 0), watermark off. */
    FDCAN1->RXF0C = ((uint32_t)RX_FIFO0_WOFFSET << FDCAN_RXF0C_F0SA_Pos)
                  | ((uint32_t)RX_FIFO0_NELEM   << FDCAN_RXF0C_F0S_Pos);

    /* Rx FIFO 1 + Rx Buffer + Tx Event FIFO unused. */
    FDCAN1->RXF1C = 0u;
    FDCAN1->RXBC  = 0u;
    FDCAN1->TXEFC = 0u;

    /* Tx: one dedicated buffer (no Tx FIFO/Queue). */
    FDCAN1->TXBC = ((uint32_t)TX_BUF_WOFFSET << FDCAN_TXBC_TBSA_Pos)
                 | ((uint32_t)TX_BUF_NELEM   << FDCAN_TXBC_NDTB_Pos);

    /* Element data-field size = 8 bytes for both Rx and Tx → Classic
     * CAN only. (For FD: bump to 7 = 64 B and re-jig the wordsize.) */
    FDCAN1->RXESC = (0u << FDCAN_RXESC_F0DS_Pos)
                  | (0u << FDCAN_RXESC_F1DS_Pos)
                  | (0u << FDCAN_RXESC_RBDS_Pos);
    FDCAN1->TXESC = (0u << FDCAN_TXESC_TBDS_Pos);

    /* Global filter: route non-matching std/ext frames to FIFO 0,
     * drop remote-frame requests (we don't model RTR). */
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
     * routes the internal Tx back to the internal Rx. No transceiver
     * needed; bare Nucleo-H753ZI is enough. */
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

    /* Push-pull, high speed, no pull. */
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
    /* APB1H bus dummy read for the standard "RCC enable then access"
     * synchronisation pattern. */
    (void)RCC->APB1HENR;

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
    /* No torn-down state to clear — leaving the peripheral parked in
     * INIT mode is enough; Can.c will re-enter Init via SetControllerMode
     * (STARTED) if requested. */
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
    /* No transceiver-standby pin on the bare Nucleo-H753ZI; numOfCtrlPins
     * is 0 in Can_Cfg.c so vendor Can.c never calls this. Keep the symbol
     * exported so the link still resolves. */
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
 * Vendor Can.c declares Can_Write but doesn't implement it (each BSP
 * does). Hth identifies the hardware Tx object handle — for us, Hth=0
 * is FDCAN1 Tx Buffer #0. The generated CanIf_Cfg.c is the only thing
 * that supplies Hth values, and it sets every TxPdu.hoh = 0 — so this
 * function only ever needs to drive buffer 0.
 */
Std_ReturnType Can_Write(Can_HwHandleType Hth, const Can_PduType *PduInfo)
{
    if (Hth != 0u) {
        return E_NOT_OK;
    }
    if (PduInfo == NULL || PduInfo->sdu == NULL) {
        return E_NOT_OK;
    }
    /* Refuse FD-sized payloads here — this build is Classic-CAN only.
     * The host-sim L2 FD path already proves the FD-on-the-wire claim
     * end-to-end; we'll wire FD on the H7 in a follow-up. */
    uint8_t dlc = PduInfo->length;
    if (dlc > 8u) {
        return E_NOT_OK;
    }

    /* If the previous TXBAR for buffer 0 hasn't drained yet (the
     * dedicated buffer is still pending), refuse — CanIf will buffer
     * via its pool and retry. */
    if ((FDCAN1->TXBRP & (1u << 0)) != 0u) {
        return CAN_BUSY;
    }

    volatile uint32_t *e = tx_buf_elem(0u);

    /* T0: 11-bit std ID shifted to bits 18..28, XTD=0 (std), RTR=0,
     * ESI=0. The generated CanIf only emits 11-bit ids for com-minimal
     * (0x100), so we don't bother with the extended-ID code path. */
    const uint32_t can_id_std11 = ((uint32_t)PduInfo->id & 0x7FFu) << 18;
    e[0] = can_id_std11;

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

    /* Request transmission of buffer 0. The M_CAN copies from the
     * MRAM into its Tx shift register asynchronously; in internal-
     * loopback this turns straight into a FIFO 0 Rx after one bit-
     * time of internal clocking. */
    FDCAN1->TXBAR = (1u << 0);

    return E_OK;
}

/* ================================================== MainFunction pump
 *
 * Vendor Can.c also leaves Can_MainFunction_Write/Read for the BSP.
 * Both are polling entrypoints CanIf calls every tick.
 *
 * - Write side: when the M_CAN has finished transmitting buffer 0
 *   (TXBTO bit 0 sets), call CanIf_TxConfirmation with the swPduHandle
 *   we stashed. We treat the dedicated buffer as a single-slot mailbox
 *   and ignore the swPduHandle bookkeeping pending an upper-layer
 *   request that needs it.
 *
 * - Read side: drain Rx FIFO 0 elements one at a time, reconstruct the
 *   canid + dlc + payload, and hand each to CanIf_RxIndication with
 *   Mailbox.Hoh = 0. CanIf does its own id-based dispatch.
 */
void Can_MainFunction_WriteChannel(uint8_t Channel)
{
    if (Channel != 0u) {
        return;
    }
    if ((FDCAN1->TXBTO & (1u << 0)) != 0u) {
        /* W1C the transmission-occurred bit so the next send re-arms. */
        FDCAN1->TXBTO = (1u << 0);
        /* CanIf_TxConfirmation expects a PduIdType. We don't track
         * outstanding TxPduIds at this layer; the dedicated-buffer
         * design has at most one in flight at a time. Pass 0 — for the
         * single-PDU com-minimal example this is exactly the only
         * TxPdu and CanIf treats it as the confirmation. */
        CanIf_TxConfirmation((PduIdType)0);
    }
}

void Can_MainFunction_Write(void)
{
    Can_MainFunction_WriteChannel(0u);
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
        const uint32_t canid =
            ((r0 & FDCAN_ELEMENT_XTD) != 0u)
              ? (r0 & 0x1FFFFFFFu)
              : ((r0 >> 18) & 0x7FFu);

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
        mailbox.Hoh          = 0u;          /* matches generated CanIf */
        info.SduLength       = dlc;
        info.SduDataPtr      = payload;
        info.MetaDataPtr     = (uint8_t *)&mailbox;
        CanIf_RxIndication(&mailbox, &info);

        /* Acknowledge — increments FIFO get-index. */
        FDCAN1->RXF0A = get_idx;
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
