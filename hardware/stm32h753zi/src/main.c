/*
 * STM32H753ZI Nucleo-144 — Com → CanIf → FDCAN1 internal loopback.
 *
 * Brings up the SAME upstream COM-stack code (vendor/as Com.c /
 * PduR.c / CanIf.c / mcal-Can.c) the L2 host-sim tests already prove,
 * compiled against the OpenVinci-emitted `examples/com-minimal`
 * config (regenerated into `generated/`). The new edges in this
 * commit are:
 *
 *   - hardware/stm32h753zi/src/Can_H7.c   — FDCAN1 backend (CanAc_*,
 *                                            Can_Write, Rx pump)
 *   - hardware/stm32h753zi/src/Can_Cfg.c  — single-controller config
 *   - hardware/stm32h753zi/src/system_init.c — PLL2Q → 80 MHz FDCAN
 *
 * Compiling cleanly with arm-none-eabi-gcc is this prompt's bar; the
 * firmware doesn't have to actually run yet. The init sequence still
 * mirrors what the host-sim L2 node does so a future smoke test on
 * real silicon doesn't need code changes here.
 *
 * USART3 diagnostic prints (PD8/PD9 → ST-LINK VCP, 115200) survive
 * so the next bring-up step has a "did it boot?" signal without the
 * CAN traffic running first.
 */

#include <stdint.h>

#include "stm32h753xx.h"

#include "Std_Types.h"
#include "Can.h"
#include "CanIf.h"
#include "PduR.h"
#include "Com.h"
#include "Com_Cfg.h"   /* generated — provides COM_SID_TxSignal etc. */

#define UART_BAUD     115200u
#define UART_PCLK_HZ  64000000u   /* HSI default — main sysclk path */

extern Can_ConfigType Can_Config;
extern void system_init_for_fdcan(void);

static void uart3_init(void);
static void uart3_puts(const char *s);
static void busy_delay(volatile uint32_t loops);

int main(void)
{
    /* PLL2Q → FDCAN kernel clock at 80 MHz. Done before Can_Init so
     * CanAc_Init's NBTP write lands on a peripheral that has its real
     * kernel clock running. */
    system_init_for_fdcan();

    /* USART3 first — gives us a heartbeat that survives even if the
     * CAN chain misbehaves below. */
    uart3_init();
    uart3_puts("openvinci-h7: boot\r\n");

    /* AUTOSAR init chain — identical shape to the L2 host-sim node
     * (tests/functional/node/node_main.c). */
    Can_Init(&Can_Config);
    CanIf_Init(NULL);
    PduR_Init(NULL);
    Com_Init(NULL);

    /* Bring the bus up. Internal-loopback mode is set inside
     * CanAc_Init; SetControllerMode(STARTED) is what calls it. */
    (void)CanIf_SetControllerMode(0u, CAN_CS_STARTED);
    (void)CanIf_SetPduMode(0u, CANIF_ONLINE);
    Com_IpduGroupStart(0u, TRUE);

    uart3_puts("openvinci-h7: stack up — sending TxSignal\r\n");

    uint8_t tx_value = 0x55u;
    uint8_t rx_value_last = 0x00u;
    uint8_t rx_value;
    uint32_t ticks_until_send = 0u;

    /* Same pump cadence as the L2 host-sim node, 1 ms tick. */
    while (1) {
        Can_MainFunction_Write();
        Can_MainFunction_Read();
        CanIf_MainFunction();
        Com_MainFunctionRx();
        Com_MainFunctionTx();

        if (ticks_until_send == 0u) {
            (void)Com_SendSignal(COM_SID_TxSignal, &tx_value);
            tx_value++;
            ticks_until_send = 100u;  /* re-arm ~100 ms */
        } else {
            ticks_until_send--;
        }

        if (E_OK == Com_ReceiveSignal(COM_SID_RxSignal, &rx_value)) {
            if (rx_value != rx_value_last) {
                /* The loopback should make 0x101 echo whatever any
                 * 0x101 sender on the (internal) bus produced. We
                 * don't drive 0x101 ourselves yet, so this branch is
                 * a no-op until a second tx path lands. */
                rx_value_last = rx_value;
                uart3_puts("openvinci-h7: RxSignal changed\r\n");
            }
        }

        busy_delay(8000u);  /* very rough 1 ms at 64 MHz / -O0 */
    }
}

/* ---- diagnostic UART (kept from PROMPT H1) -------------------------- */

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

static void uart3_putc(char c)
{
    while ((USART3->ISR & USART_ISR_TXE_TXFNF) == 0u) { }
    USART3->TDR = (uint8_t)c;
}

static void uart3_puts(const char *s)
{
    while (*s) {
        uart3_putc(*s++);
    }
}

/* newlib-nano init / fini stubs. */
void _init(void) { }
void _fini(void) { }

static void busy_delay(volatile uint32_t loops)
{
    while (loops--) { }
}
