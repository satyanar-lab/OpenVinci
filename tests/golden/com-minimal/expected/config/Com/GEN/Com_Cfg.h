/**
 * SSAS - Simple Smart Automotive Software
 * Copyright (C) 2021-<YEAR> Parai Wang <parai@foxmail.com>
 *
 * Generated at <TIMESTAMP>
 */
#ifndef COM_CFG_H
#define COM_CFG_H
/* ================================ [ INCLUDES  ] ============================================== */
/* ================================ [ MACROS    ] ============================================== */
#ifndef COM_CONST
#define COM_CONST
#endif

#ifndef COM_MAIN_FUNCTION_PERIOD
#define COM_MAIN_FUNCTION_PERIOD 10u
#endif
#define COM_CONVERT_MS_TO_MAIN_CYCLES(x) \
  ((x + COM_MAIN_FUNCTION_PERIOD - 1u) / COM_MAIN_FUNCTION_PERIOD)

#define COM_USE_CAN
#define COM_USE_SIGNAL_CONFIG
#define COM_USE_SIGNAL_UPDATE_BIT

#define COM_RX_FOR_CAN0(id, PduInfoPtr) \
  if (0x101 == id) { \
    Com_RxIndication(COM_CAN0_RX_MSG, PduInfoPtr); \
  }

#ifndef COM_ECUC_PDUID_OFFSET
#define COM_ECUC_PDUID_OFFSET 0
#endif

/* NOTE: manually modify to fix it to the right HTH */
#define COM_ECUC_CAN0_PDUID_MIN COM_ECUC_PDUID_OFFSET
#define COM_ECUC_CAN0_PDUID_MAX COM_ECUC_PDUID_OFFSET + 2
#define COM_TX_FOR_CAN0(TxPduId, dlPdu, PduInfoPtr, ret) \
  if ((COM_CAN0_TX_MSG+COM_ECUC_PDUID_OFFSET) == TxPduId) { \
    dlPdu.id = 0x100; \
    ret = Can_Write(0, &dlPdu); \
  }

/* messages for network CAN0 */
#define COM_CAN0_TX_MSG 0
#define COM_CAN0_RX_MSG 1

/* signals for network CAN0 */
/* signals for network CAN0 message TX_MSG: id=0x100 dlc=8, dir=TX */
#define COM_SID_TxSignal 0 /* little 8@0 */

/* signals for network CAN0 message RX_MSG: id=0x101 dlc=8, dir=RX */
#define COM_SID_RxSignal 1 /* little 8@0 */


/* NOTE: manually modify to create more groups */
#define COM_GROUP_ID_CAN0 0
#define Com_IPduTX_MSG_GroupRefMask (1<<COM_GROUP_ID_CAN0)
#define Com_IPduRX_MSG_GroupRefMask (1<<COM_GROUP_ID_CAN0)

#define COM_GROUP_ID_MAX 1

#define COM_USE_MAIN_FAST

// #define COM_USE_PB_CONFIG

/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
/* ================================ [ LOCALS    ] ============================================== */
/* ================================ [ FUNCTIONS ] ============================================== */
#endif /* COM_CFG_H */
