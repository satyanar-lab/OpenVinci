/*
 * board.c — Nucleo-H753ZI USART3 / GPIO helpers.
 *
 * Same USART3 setup the original src/main.c had (PD8/PD9 AF7,
 * 115200 8N1 over the ST-LINK VCP). Lifted out so the generated
 * App seam can print without re-implementing UART, and so we have
 * exactly one place to change the baud / pins per board.
 *
 * Clock assumption: HSI 64 MHz default sysclk. The generated EcuM
 * calls system_init_for_fdcan() *before* board_init(), but that
 * function only brings PLL2Q up for FDCAN — sysclk stays at HSI 64
 * MHz, which is what UART_PCLK_HZ encodes.
 */

#include <stdint.h>

#include "stm32h753xx.h"

#include "board.h"

#define UART_BAUD     115200u
#define UART_PCLK_HZ  64000000u

static void uart3_init(void)
{
    RCC->AHB4ENR  |= RCC_AHB4ENR_GPIODEN;
    RCC->APB1LENR |= RCC_APB1LENR_USART3EN;

    GPIOD->MODER &= ~(GPIO_MODER_MODE8_Msk | GPIO_MODER_MODE9_Msk);
    GPIOD->MODER |=  (2u << GPIO_MODER_MODE8_Pos)
                  |  (2u << GPIO_MODER_MODE9_Pos);

    GPIOD->AFR[1] &= ~(GPIO_AFRH_AFSEL8_Msk | GPIO_AFRH_AFSEL9_Msk);
    GPIOD->AFR[1] |=  (7u << GPIO_AFRH_AFSEL8_Pos)
                  |   (7u << GPIO_AFRH_AFSEL9_Pos);

    USART3->BRR = (UART_PCLK_HZ + (UART_BAUD / 2u)) / UART_BAUD;
    USART3->CR1 = USART_CR1_UE | USART_CR1_TE;
    while ((USART3->ISR & USART_ISR_TEACK) == 0u) { }
}

void board_init(void)
{
    uart3_init();
}

static void uart3_putc(char c)
{
    while ((USART3->ISR & USART_ISR_TXE_TXFNF) == 0u) { }
    USART3->TDR = (uint8_t)c;
}

void board_vcp_puts(const char *s)
{
    while (*s) {
        uart3_putc(*s++);
    }
}

void board_vcp_put_hex8(uint8_t v)
{
    static const char hex[] = "0123456789ABCDEF";
    uart3_putc(hex[(v >> 4) & 0x0Fu]);
    uart3_putc(hex[v & 0x0Fu]);
}

/* newlib-nano calls these from __libc_init_array. We have no global
 * C++ ctors / .init_array entries to run, so both can stay empty.
 * Live here rather than in the generated glue so swapping APP_VARIANT
 * doesn't lose them. */
void _init(void) { }
void _fini(void) { }
