/*
 * Minimal clock setup for the FDCAN demo.
 *
 * Default state after reset (per RM0433 §8 / system_stm32h7xx.c):
 *   HSI  = 64 MHz, sysclk = HSI, HPRE = /1, D2PPRE1 = /1, all PLLs off.
 *
 * That gives 64 MHz to USART3 (used by `main.c`'s heartbeat), but
 * FDCAN's kernel-clock mux (RCC.D2CCIP1R.FDCANSEL) can only pick
 * HSE / PLL1Q / PLL2Q. The Nucleo-H753ZI has an 8 MHz HSE input but
 * we don't want to depend on a board-specific oscillator at this
 * stage — so this file brings up PLL2Q sourced from HSI and routes
 * FDCAN to it at exactly 80 MHz, the rate the bit-timing math in
 * Can_H7.c was sized for.
 *
 * PLL2 math:
 *   HSI / DIVM2 = 64 MHz / 8 = 8 MHz   (PLL2 input — must be 1..16 MHz)
 *   × DIVN2     = 8 × 40    = 320 MHz  (VCO — wide-VCO range 150..420)
 *   ÷ DIVQ2     = 320 / 4   = 80 MHz   (Q output → FDCAN kernel clock)
 */

#include "stm32h753xx.h"

static void pll2_enable_for_fdcan(void)
{
    /* PLL2 source = HSI (already on after reset). */
    RCC->PLLCKSELR &= ~RCC_PLLCKSELR_PLLSRC_Msk;       /* 00 = HSI */
    RCC->PLLCKSELR |= (8u << RCC_PLLCKSELR_DIVM2_Pos); /* DIVM2 = 8  */

    /* PLL2 input range = 4..8 MHz (8 MHz lands here),
     * VCO = wide range (150..420 MHz; 320 MHz fits), Q output enabled.
     * P and R are unused. */
    RCC->PLLCFGR =
        (RCC->PLLCFGR & ~(RCC_PLLCFGR_PLL2RGE_Msk
                        | RCC_PLLCFGR_PLL2VCOSEL_Msk
                        | RCC_PLLCFGR_DIVP2EN
                        | RCC_PLLCFGR_DIVQ2EN
                        | RCC_PLLCFGR_DIVR2EN))
      | (2u << RCC_PLLCFGR_PLL2RGE_Pos)
      | RCC_PLLCFGR_DIVQ2EN;

    /* Multipliers / dividers for PLL2. The DIVN field is encoded as
     * "value - 1"; DIVQ likewise. */
    RCC->PLL2DIVR =
        ((40u - 1u) << RCC_PLL2DIVR_N2_Pos)
      | ((4u  - 1u) << RCC_PLL2DIVR_Q2_Pos);

    /* Spin PLL2 up. */
    RCC->CR |= RCC_CR_PLL2ON;
    while ((RCC->CR & RCC_CR_PLL2RDY) == 0u) { }

    /* Route the FDCAN kernel clock to PLL2Q (FDCANSEL = 10). */
    RCC->D2CCIP1R = (RCC->D2CCIP1R & ~RCC_D2CCIP1R_FDCANSEL_Msk)
                  | (2u << RCC_D2CCIP1R_FDCANSEL_Pos);
}

void system_init_for_fdcan(void)
{
    pll2_enable_for_fdcan();
}
