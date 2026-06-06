/**
 * SSAS - Simple Smart Automotive Software
 * Copyright (C) 2021-<YEAR> Parai Wang <parai@foxmail.com>
 *
 * Generated at <TIMESTAMP>
 */
/* ================================ [ INCLUDES  ] ============================================== */
#include "Com_Cfg.h"
#include "Com.h"
#include "Com_Priv.h"
#ifdef USE_PDUR
#include "PduR_Cfg.h"
#endif
/* ================================ [ MACROS    ] ============================================== */
/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
static const uint8_t TxFdSignal_InitialValue[16] = { 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0,  };
static const uint8_t RxFdSignal_InitialValue[16] = { 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0,  };

static uint8_t Com_PduData_TX_FD_MSG[16];
static uint8_t Com_PduData_RX_FD_MSG[16];

static Com_IPduTxContextType Com_IPduTxContext_TX_FD_MSG;
static Com_IPduRxContextType Com_IPduRxContext_RX_FD_MSG;

#ifdef COM_USE_SIGNAL_CONFIG
static const Com_SignalTxConfigType Com_SignalTxConfig_TxFdSignal = {
  #ifdef COM_USE_SIGNAL_TX_ERROR_NOTIFICATION
  NULL, /* ErrorNotification */
  #endif
  #ifdef COM_USE_SIGNAL_TX_NOTIFICATION
  NULL, /* TxNotification */
  #endif
  #if !defined(COM_USE_SIGNAL_TX_ERROR_NOTIFICATION) && !defined(COM_USE_SIGNAL_TX_NOTIFICATION)
  0,
  #endif
};

static Com_SignalRxContextType Com_SignalRxContext_RxFdSignal;
static const Com_SignalRxConfigType Com_SignalRxConfig_RxFdSignal = {
  &Com_SignalRxContext_RxFdSignal,
  #ifdef COM_USE_SIGNAL_RX_INVALID_NOTIFICATION
  NULL, /* InvalidNotification */
  #endif
  #ifdef COM_USE_SIGNAL_RX_NOTIFICATION
  NULL, /* RxNotification */
  #endif
  #ifdef COM_USE_SIGNAL_RX_TIMEOUT
  NULL, /* RxTOut */
  #endif
  NULL, /* TimeoutSubstitutionValue */
  0, /* FirstTimeout */
  0, /* Timeout */
  COM_ACTION_NOTIFY, /* DataInvalidAction */
  COM_ACTION_NONE, /* RxDataTimeoutAction */
};

#endif /* COM_USE_SIGNAL_CONFIG */
static const Com_SignalConfigType Com_SignalConfigs[] = {
  {
#ifdef USE_SHELL
    "TxFdSignal",
#endif
    &Com_PduData_TX_FD_MSG[0], /* ptr */
    TxFdSignal_InitialValue, /* initPtr */
#ifdef COM_USE_SIGNAL_CONFIG
    NULL, /* rxConfig */
    &Com_SignalTxConfig_TxFdSignal, /* txConfig */
#endif
    COM_SID_TxFdSignal, /* HandleId */
    COM_CAN0_TX_FD_MSG, /* PduId */
    0, /* BitPosition */
    128, /* BitSize */
#ifdef COM_USE_SIGNAL_UPDATE_BIT
    COM_UPDATE_BIT_NOT_USED, /* UpdateBit */
#endif
    COM_UINT8N, /* type */
    COM_LITTLE_ENDIAN, /* Endianness */
    FALSE,
  },
  {
#ifdef USE_SHELL
    "RxFdSignal",
#endif
    &Com_PduData_RX_FD_MSG[0], /* ptr */
    RxFdSignal_InitialValue, /* initPtr */
#ifdef COM_USE_SIGNAL_CONFIG
    &Com_SignalRxConfig_RxFdSignal, /* rxConfig */
    NULL, /* txConfig */
#endif
    COM_SID_RxFdSignal, /* HandleId */
    COM_CAN0_RX_FD_MSG, /* PduId */
    0, /* BitPosition */
    128, /* BitSize */
#ifdef COM_USE_SIGNAL_UPDATE_BIT
    COM_UPDATE_BIT_NOT_USED, /* UpdateBit */
#endif
    COM_UINT8N, /* type */
    COM_LITTLE_ENDIAN, /* Endianness */
    FALSE,
  },
};

static const Com_SignalConfigType* Com_IPduSignals_TX_FD_MSG[] = {
  &Com_SignalConfigs[COM_SID_TxFdSignal],
};

static const Com_SignalConfigType* Com_IPduSignals_RX_FD_MSG[] = {
  &Com_SignalConfigs[COM_SID_RxFdSignal],
};

static const Com_IPduTxConfigType Com_IPduTxConfig_TX_FD_MSG = {
  &Com_IPduTxContext_TX_FD_MSG,
  #ifdef COM_USE_TX_ERROR_NOTIFICATION
  NULL, /* ErrorNotification */
  #endif
  #ifdef COM_USE_TX_NOTIFICATION
  NULL, /* TxNotification */
  #endif
  #ifdef COM_USE_TX_IPDU_CALLOUT
  NULL, /* TxIpduCallout */
  #endif
  COM_CONVERT_MS_TO_MAIN_CYCLES(0u), /* FirstTime */
  COM_CONVERT_MS_TO_MAIN_CYCLES(1000u), /* CycleTime */
#ifdef USE_PDUR
  PDUR_CAN0_TX_FD_MSG,
#else
  COM_ECUC_PDUID_OFFSET + COM_CAN0_TX_FD_MSG,
#endif
};

static const Com_IPduRxConfigType Com_IPduRxConfig_RX_FD_MSG = {
  &Com_IPduRxContext_RX_FD_MSG,
  #ifdef COM_USE_RX_NOTIFICATION
  NULL, /* RxNotification */
  #endif
  #ifdef COM_USE_RX_TIMEOUT
  NULL, /* RxTOut */
  #endif
  #ifdef COM_USE_RX_IPDU_CALLOUT
  NULL, /* RxIpduCallout */
  #endif
  COM_CONVERT_MS_TO_MAIN_CYCLES(0u), /* FirstTimeout */
  COM_CONVERT_MS_TO_MAIN_CYCLES(0u), /* Timeout */
};

static const Com_IPduConfigType Com_IPduConfigs[] = {
  {
#ifdef USE_SHELL
    "TX_FD_MSG",
#endif
    Com_PduData_TX_FD_MSG, /* ptr */
    NULL, /* dynLen */
    Com_IPduSignals_TX_FD_MSG, /* signals */
    NULL, /* rxConfig */
    &Com_IPduTxConfig_TX_FD_MSG, /* txConfig */
    Com_IPduTX_FD_MSG_GroupRefMask,
    sizeof(Com_PduData_TX_FD_MSG), /* length */
    ARRAY_SIZE(Com_IPduSignals_TX_FD_MSG), /* numOfSignals */
  },
  {
#ifdef USE_SHELL
    "RX_FD_MSG",
#endif
    Com_PduData_RX_FD_MSG, /* ptr */
    NULL, /* dynLen */
    Com_IPduSignals_RX_FD_MSG, /* signals */
    &Com_IPduRxConfig_RX_FD_MSG, /* rxConfig */
    NULL, /* txConfig */
    Com_IPduRX_FD_MSG_GroupRefMask,
    sizeof(Com_PduData_RX_FD_MSG), /* length */
    ARRAY_SIZE(Com_IPduSignals_RX_FD_MSG), /* numOfSignals */
  },
};

static Com_GlobalContextType Com_GlobalContext;
const Com_ConfigType Com_Config = {
  Com_IPduConfigs,
  Com_SignalConfigs,
  &Com_GlobalContext,
  ARRAY_SIZE(Com_IPduConfigs),
  ARRAY_SIZE(Com_SignalConfigs),
  1 /* numOfGroups */,
};

/* ================================ [ LOCALS    ] ============================================== */
/* ================================ [ FUNCTIONS ] ============================================== */
#ifdef USE_E2E
#include "E2E.h"
#include "E2E_Cfg.h"
#endif /* USE_E2E */

