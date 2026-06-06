/**
 * SSAS - Simple Smart Automotive Software
 * Copyright (C) 2021-<YEAR> Parai Wang <parai@foxmail.com>
 *
 * Generated at <TIMESTAMP>
 */
#ifndef CANTP_CFG_H
#define CANTP_CFG_H
/* ================================ [ INCLUDES  ] ============================================== */
/* ================================ [ MACROS    ] ============================================== */
#ifndef CANIF_CANTP_BASEID
#define CANIF_CANTP_BASEID 0
#endif

#define CANTP_ISO_TP_RX 0
#define CANTP_ISO_TP_TX 0
#ifndef USE_CANIF
#define CANIF_ISO_TP_TX (CANIF_CANTP_BASEID+0)
#endif


#define CANTP_USE_TX_CONFIRMATION

/* #define CANTP_USE_STD_TIMER */

#define CANTP_STMIN_ADJUST 0u
#ifndef CANTP_MAIN_FUNCTION_PERIOD
#define CANTP_MAIN_FUNCTION_PERIOD 10u
#endif
#define CANTP_CONVERT_MS_TO_MAIN_CYCLES(x)  \
  ((x + CANTP_MAIN_FUNCTION_PERIOD - 1u) / CANTP_MAIN_FUNCTION_PERIOD)
// #define CANTP_USE_PB_CONFIG

/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
/* ================================ [ LOCALS    ] ============================================== */
/* ================================ [ FUNCTIONS ] ============================================== */
#endif /* CANTP_CFG_H */
