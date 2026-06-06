/**
 * SSAS - Simple Smart Automotive Software
 * Copyright (C) 2021-<YEAR> Parai Wang <parai@foxmail.com>
 *
 * Generated at <TIMESTAMP>
 */
/* ================================ [ INCLUDES  ] ============================================== */
#include "PduR.h"
#include "PduR_Cfg.h"
#include "PduR_Priv.h"
#include "CanTp.h"
#include "CanTp_Cfg.h"
#include "Dcm.h"
#include "Dcm_Cfg.h"
/* ================================ [ MACROS    ] ============================================== */
/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
const PduR_ApiType PduR_DcmApi = {
  Dcm_StartOfReception,
  Dcm_CopyRxData,
  Dcm_TpRxIndication,
  NULL,
  NULL,
  Dcm_CopyTxData,
  Dcm_TpTxConfirmation,
};

const PduR_ApiType PduR_CanTpApi = {
  NULL,
  NULL,
  NULL,
  NULL,
  CanTp_Transmit,
  NULL,
  NULL,
};

static const PduR_PduType PduR_SrcPdu_CanTp_Dcm_ISO_TP_RX = {
  PDUR_MODULE_CANTP,
  CANTP_ISO_TP_RX,
  &PduR_CanTpApi,
};

static const PduR_PduType PduR_DstPdu_CanTp_Dcm_ISO_TP_RX[]={
  {
    PDUR_MODULE_DCM,
    DCM_ISO_TP_RX,
    &PduR_DcmApi,
  },
};

static const PduR_PduType PduR_SrcPdu_Dcm_CanTp_ISO_TP_TX = {
  PDUR_MODULE_DCM,
  DCM_ISO_TP_TX,
  &PduR_DcmApi,
};

static const PduR_PduType PduR_DstPdu_Dcm_CanTp_ISO_TP_TX[]={
  {
    PDUR_MODULE_CANTP,
    CANTP_ISO_TP_TX,
    &PduR_CanTpApi,
  },
};

static const PduR_RoutingPathType PduR_RoutingPaths[] = {
  { /* 0: PDU ISO_TP_RX from CanTp to Dcm ISO_TP_RX */
    &PduR_SrcPdu_CanTp_Dcm_ISO_TP_RX,
    PduR_DstPdu_CanTp_Dcm_ISO_TP_RX,
    NULL, NULL, 0,
    ARRAY_SIZE(PduR_DstPdu_CanTp_Dcm_ISO_TP_RX),
  },
  { /* 1: PDU ISO_TP_TX from Dcm to CanTp ISO_TP_TX */
    &PduR_SrcPdu_Dcm_CanTp_ISO_TP_TX,
    PduR_DstPdu_Dcm_CanTp_ISO_TP_TX,
    NULL, NULL, 0,
    ARRAY_SIZE(PduR_DstPdu_Dcm_CanTp_ISO_TP_TX),
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
