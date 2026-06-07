/**
 * SSAS - Simple Smart Automotive Software
 * Copyright (C) 2021-<YEAR> Parai Wang <parai@foxmail.com>
 *
 */
/* ================================ [ INCLUDES  ] ============================================== */
#include "PduR.h"
#include "PduR_Cfg.h"
#include "PduR_Priv.h"
#include "Com.h"
#include "Com_Cfg.h"
#include "CanIf.h"
#include "CanIf_Cfg.h"
/* ================================ [ MACROS    ] ============================================== */
/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
const PduR_ApiType PduR_ComApi = {
  Com_StartOfReception,
  Com_CopyRxData,
  Com_TpRxIndication,
  Com_RxIndication,
  NULL,
  Com_CopyTxData,
  Com_TxConfirmation,
};

const PduR_ApiType PduR_CanIfApi = {
  NULL,
  NULL,
  NULL,
  NULL,
  CanIf_Transmit,
  NULL,
  NULL,
};

static const PduR_PduType PduR_SrcPdu_Com_CanIf_CAN0_TX_MSG = {
  PDUR_MODULE_COM,
  COM_CAN0_TX_MSG,
  &PduR_ComApi,
};

static const PduR_PduType PduR_DstPdu_Com_CanIf_CAN0_TX_MSG[]={
  {
    PDUR_MODULE_CANIF,
    CANIF_CAN0_TX_MSG,
    &PduR_CanIfApi,
  },
};

static const PduR_PduType PduR_SrcPdu_CanIf_Com_CAN0_RX_MSG = {
  PDUR_MODULE_CANIF,
  CANIF_CAN0_RX_MSG,
  &PduR_CanIfApi,
};

static const PduR_PduType PduR_DstPdu_CanIf_Com_CAN0_RX_MSG[]={
  {
    PDUR_MODULE_COM,
    COM_CAN0_RX_MSG,
    &PduR_ComApi,
  },
};

static const PduR_RoutingPathType PduR_RoutingPaths[] = {
  { /* 0: PDU CAN0_TX_MSG from Com to CanIf CAN0_TX_MSG */
    &PduR_SrcPdu_Com_CanIf_CAN0_TX_MSG,
    PduR_DstPdu_Com_CanIf_CAN0_TX_MSG,
    NULL, NULL, 0,
    ARRAY_SIZE(PduR_DstPdu_Com_CanIf_CAN0_TX_MSG),
  },
  { /* 1: PDU CAN0_RX_MSG from CanIf to Com CAN0_RX_MSG */
    &PduR_SrcPdu_CanIf_Com_CAN0_RX_MSG,
    PduR_DstPdu_CanIf_Com_CAN0_RX_MSG,
    NULL, NULL, 0,
    ARRAY_SIZE(PduR_DstPdu_CanIf_Com_CAN0_RX_MSG),
  },
};

const PduR_ConfigType PduR_Config = {
#if defined(PDUR_USE_MEMPOOL)
  NULL,
#endif
  PduR_RoutingPaths,
  ARRAY_SIZE(PduR_RoutingPaths),
};
/* ================================ [ LOCALS    ] ============================================== */
/* ================================ [ FUNCTIONS ] ============================================== */
