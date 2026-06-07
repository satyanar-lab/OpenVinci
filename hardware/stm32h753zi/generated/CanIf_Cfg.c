/**
 * SSAS - Simple Smart Automotive Software
 * Copyright (C) 2021-2026 Parai Wang <parai@foxmail.com>
 *
 */
/* ================================ [ INCLUDES  ] ============================================== */
#include "CanIf.h"
#include "CanIf_Cfg.h"
#include "CanIf_Priv.h"
#include "PduR_CanIf.h"
#include "PduR_Cfg.h"
/* ================================ [ MACROS    ] ============================================== */
/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
static const CanIf_RxPduType CanIf_RxPdus_CAN0[] = {
  {
    PduR_CanIfRxIndication,
    PDUR_CAN0_RX_MSG,
    0x100, /* canid */
    0x1fffffff, /* mask */
    0, /* hoh */
  },
};

static const CanIf_TxPduType CanIf_TxPdus[] = {
  {
    PduR_CanIfTxConfirmation,
    PDUR_CAN0_TX_MSG,
    0x100, /* canid */
    NULL, /* p_canid */
    0, /* hoh */
    0, /* ControllerId */
    #if CANIF_TX_PACKET_POOL_SIZE > 0
    FALSE, /* bUseTxPool */
    #endif
  },
};

static CanIf_CtrlContextType CanIf_CtrlContexts[1];
static const CanIf_CtrlConfigType CanIf_CtrlConfigs[] = {
  {
    CanIf_RxPdus_CAN0,
    ARRAY_SIZE(CanIf_RxPdus_CAN0),
    #if defined(CANIF_USE_TX_TIMEOUT) && defined(USE_CANSM)
    CANIF_CONVERT_MS_TO_MAIN_CYCLES(100u),
    #endif
  },
};
const CanIf_ConfigType CanIf_Config = {
  CanIf_TxPdus,
  CanIf_CtrlContexts,
  CanIf_CtrlConfigs,
  ARRAY_SIZE(CanIf_TxPdus),
  ARRAY_SIZE(CanIf_CtrlContexts),
};

/* ================================ [ LOCALS    ] ============================================== */
/* ================================ [ FUNCTIONS ] ============================================== */
