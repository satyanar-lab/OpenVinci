/**
 * SSAS - Simple Smart Automotive Software
 * Copyright (C) 2021-<YEAR> Parai Wang <parai@foxmail.com>
 *
 * Generated at <TIMESTAMP>
 */
#ifndef CANIF_CFG_H
#define CANIF_CFG_H
/* ================================ [ INCLUDES  ] ============================================== */
/* ================================ [ MACROS    ] ============================================== */
#define CANIF_CHL_CAN0 0u

#define CANIF_ISO_TP_RX 0u /* CAN0 id=0x7e0 */

#define CANIF_ISO_TP_TX 0u /* CAN0 id=0x7e8 */
#ifndef CANIF_MAIN_FUNCTION_PERIOD
#define CANIF_MAIN_FUNCTION_PERIOD 10u
#endif
#define CANIF_CONVERT_MS_TO_MAIN_CYCLES(x) \
  ((x + CANIF_MAIN_FUNCTION_PERIOD - 1u) / CANIF_MAIN_FUNCTION_PERIOD)

#define CANIF_USE_TX_TIMEOUT

// #define CANIF_USE_PB_CONFIG

// #define CANIF_USE_TX_CALLOUT

// #define CANIF_USE_RX_CALLOUT

#ifndef CANIF_RX_PACKET_POOL_SIZE
#define CANIF_RX_PACKET_POOL_SIZE 0u
#endif

#ifndef CANIF_TX_PACKET_POOL_SIZE
#define CANIF_TX_PACKET_POOL_SIZE 0u
#endif

#ifndef CANIF_RX_PACKET_DATA_SIZE
#define CANIF_RX_PACKET_DATA_SIZE 64u
#endif

#ifndef CANIF_TX_PACKET_DATA_SIZE
#define CANIF_TX_PACKET_DATA_SIZE 64u
#endif

/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
/* ================================ [ LOCALS    ] ============================================== */
/* ================================ [ FUNCTIONS ] ============================================== */
#endif /* CANIF_CFG_H */
