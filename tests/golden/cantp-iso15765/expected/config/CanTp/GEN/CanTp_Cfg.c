/**
 * SSAS - Simple Smart Automotive Software
 * Copyright (C) 2021-<YEAR> Parai Wang <parai@foxmail.com>
 *
 * Generated at <TIMESTAMP>
 */
/* ================================ [ INCLUDES  ] ============================================== */
#ifdef USE_CANIF
#include "CanIf_Cfg.h"
#endif
#include "CanTp_Cfg.h"
#include "CanTp.h"
#include "CanTp_Priv.h"
#include "PduR_Cfg.h"
#ifdef PDUR_DCM_CANTP_ZERO_COST
#include "Dcm_Cfg.h"
#endif
/* ================================ [ MACROS    ] ============================================== */
#ifndef CANTP_LL_DL
#define CANTP_LL_DL 8u
#endif

#ifndef CANTP_CFG_PADDING
#define CANTP_CFG_PADDING 0x55u
#endif

#if defined(_WIN32) || defined(linux)
#define L_CONST
#else
#define L_CONST const
#endif
/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
static uint8_t u8ISO_TPData[8];
static L_CONST CanTp_ChannelConfigType CanTpChannelConfigs[] = {
  {
    /* ISO_TP */
    u8ISO_TPData,
    CANTP_STANDARD,
    CANIF_ISO_TP_TX,
    #ifdef PDUR_DCM_CANTP_ZERO_COST
    DCM_ISO_TP_RX /* PduR_RxPduId */,
    DCM_ISO_TP_TX /* PduR_TxPduId */,
    #else
    PDUR_ISO_TP_RX /* PduR_RxPduId */,
    PDUR_ISO_TP_TX /* PduR_TxPduId */,
    #endif
    CANTP_CONVERT_MS_TO_MAIN_CYCLES(25u), /* N_As */
    CANTP_CONVERT_MS_TO_MAIN_CYCLES(1000u), /* N_Bs */
    CANTP_CONVERT_MS_TO_MAIN_CYCLES(1000u), /* N_Cr */
    0u, /* STmin */
    0u, /* BS */
    0u, /* N_TA */
    8u, /* WftMax */
    8, /* LL_DL */
    0xCCu, /* padding */
    CANTP_PHYSICAL, /* comType */
  },
};

static CanTp_ChannelContextType CanTpChannelContexts[ARRAY_SIZE(CanTpChannelConfigs)];

const CanTp_ConfigType CanTp_Config = {
  CanTpChannelConfigs,
  CanTpChannelContexts,
  ARRAY_SIZE(CanTpChannelConfigs),
};
/* ================================ [ LOCALS    ] ============================================== */
#if defined(_WIN32) || defined(linux)
#include <stdlib.h>
static void __attribute__((constructor)) _ll_dl_init(void) {
  int i;
  char *llDlStr = getenv("LL_DL");
  if (llDlStr != NULL) {
    for( i = 0; i < ARRAY_SIZE(CanTpChannelConfigs); i++ ) {
      CanTpChannelConfigs[i].LL_DL = atoi(llDlStr);
    }
  }
}
#endif
/* ================================ [ FUNCTIONS ] ============================================== */
