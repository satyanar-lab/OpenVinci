/*
 * STM32H753ZI Nucleo-144 — "hello" over the on-board ST-LINK VCP.
 *
 * After reset, the H7 boots at HSI = 64 MHz (HSI64 is the default
 * sysclk source; HPRE/D2PPRE1 are /1). USART3 is on D2 / APB1 and
 * its default kernel clock is PCLK1 = 64 MHz. cmsis-device-h7's
 * `system_stm32h7xx.c::SystemInit()` is called from the startup
 * `.s` file before main() — we leave its defaults alone here.
 *
 * On the Nucleo-H753ZI, ST-LINK's Virtual COM Port is wired to
 * USART3 TX/RX on PD8 / PD9 (alternate function 7). Host enumerates
 * the board as /dev/ttyACM0 (Linux) / /dev/cu.usbmodem* (macOS) /
 * a COM port (Windows). Open at 115200 8N1, no flow control.
 *
 * This file proves the cross-build path only — there is no CAN code
 * yet. Adding FDCAN against OpenVinci's generated stack is PROMPT H2.
 */

#include "stm32h753xx.h"

#define UART_BAUD     115200u
/* PCLK1 = HSI / (HPRE * D2PPRE1) = 64 MHz / (1 * 1) at reset. */
#define UART_PCLK_HZ  64000000u

static void uart3_init(void);
static void uart3_putc(char c);
static void uart3_puts(const char *s);
static void busy_delay(volatile uint32_t loops);

int main(void)
{
    uart3_init();

    /* Hello, with line endings ST-LINK's VCP shows verbatim. */
    while (1) {
        uart3_puts("hello\r\n");
        busy_delay(4000000u);
    }
}

static void uart3_init(void)
{
    /* Clock the GPIOD port (AHB4) and USART3 (APB1L). */
    RCC->AHB4ENR  |= RCC_AHB4ENR_GPIODEN;
    RCC->APB1LENR |= RCC_APB1LENR_USART3EN;

    /* PD8 (USART3_TX) and PD9 (USART3_RX): alternate-function mode,
     * AF7 selects USART3 (RM0433 §57.4.16 / pin assignment tables).
     */
    GPIOD->MODER &= ~(GPIO_MODER_MODE8_Msk | GPIO_MODER_MODE9_Msk);
    GPIOD->MODER |=  (2u << GPIO_MODER_MODE8_Pos)
                  |  (2u << GPIO_MODER_MODE9_Pos);

    GPIOD->AFR[1] &= ~(GPIO_AFRH_AFSEL8_Msk | GPIO_AFRH_AFSEL9_Msk);
    GPIOD->AFR[1] |=  (7u << GPIO_AFRH_AFSEL8_Pos)
                  |   (7u << GPIO_AFRH_AFSEL9_Pos);

    /* Oversampling x16 (USART_CR1.OVER8=0 default) → BRR = fck/baud.
     * Round-to-nearest so 64 MHz / 115200 = 555.55 → 556 = 0x22C.
     */
    USART3->BRR = (UART_PCLK_HZ + (UART_BAUD / 2u)) / UART_BAUD;

    /* Enable TX path. RX is wired through but unused for "hello". */
    USART3->CR1 = USART_CR1_UE | USART_CR1_TE;

    /* Wait for transmitter to be ready before the first putc. */
    while ((USART3->ISR & USART_ISR_TEACK) == 0u) { }
}

static void uart3_putc(char c)
{
    /* TXFNF is the H7 alias for "TX FIFO not full" (CMSIS uses
     * USART_ISR_TXE_TXFNF). When FIFO is disabled, this behaves as
     * the classic TXE bit. */
    while ((USART3->ISR & USART_ISR_TXE_TXFNF) == 0u) { }
    USART3->TDR = (uint8_t)c;
}

static void uart3_puts(const char *s)
{
    while (*s) {
        uart3_putc(*s++);
    }
}

/* newlib-nano's __libc_init_array (called from Reset_Handler in the
 * cmsis-device-h7 startup) invokes these to run global ctors/dtors.
 * Pure-C firmware has none — empty stubs satisfy the linker without
 * pulling in extra runtime.
 */
void _init(void) { }
void _fini(void) { }

/* Hand-rolled busy delay. ~64 MHz core and an empty volatile loop
 * works out at very roughly one cycle per iteration with -O0; close
 * enough to print every second. We'll replace this with SysTick once
 * the CAN code lands and we actually need timing accuracy.
 */
static void busy_delay(volatile uint32_t loops)
{
    while (loops--) { }
}
