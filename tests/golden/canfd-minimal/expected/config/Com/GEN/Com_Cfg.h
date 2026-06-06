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
  if (0x201 == id) { \
    Com_RxIndication(COM_CAN0_RX_FD_MSG, PduInfoPtr); \
  }

#ifndef COM_ECUC_PDUID_OFFSET
#define COM_ECUC_PDUID_OFFSET 0
#endif

/* NOTE: manually modify to fix it to the right HTH */
#define COM_ECUC_CAN0_PDUID_MIN COM_ECUC_PDUID_OFFSET
#define COM_ECUC_CAN0_PDUID_MAX COM_ECUC_PDUID_OFFSET + 2
#define COM_TX_FOR_CAN0(TxPduId, dlPdu, PduInfoPtr, ret) \
  if ((COM_CAN0_TX_FD_MSG+COM_ECUC_PDUID_OFFSET) == TxPduId) { \
    dlPdu.id = 0x200; \
    ret = Can_Write(0, &dlPdu); \
  }

/* messages for network CAN0 */
#define COM_CAN0_TX_FD_MSG 0
#define COM_CAN0_RX_FD_MSG 1

/* signals for network CAN0 */
/* signals for network CAN0 message TX_FD_MSG: id=0x200 dlc=16, dir=TX */
#define COM_SID_TxFdSignal 0 /* little 128@0 */

/* signals for network CAN0 message RX_FD_MSG: id=0x201 dlc=16, dir=RX */
#define COM_SID_RxFdSignal 1 /* little 128@0 */


/* NOTE: manually modify to create more groups */
#define COM_GROUP_ID_CAN0 0
#define Com_IPduTX_FD_MSG_GroupRefMask (1<<COM_GROUP_ID_CAN0)
#define Com_IPduRX_FD_MSG_GroupRefMask (1<<COM_GROUP_ID_CAN0)

#define COM_GROUP_ID_MAX 1

#define COM_USE_MAIN_FAST

// #define COM_USE_PB_CONFIG

/* ================================ [ TYPES     ] ============================================== */
/* ================================ [ DECLARES  ] ============================================== */
/* ================================ [ DATAS     ] ============================================== */
/* ================================ [ LOCALS    ] ============================================== */
/* ================================ [ FUNCTIONS ] ============================================== */
#endif /* COM_CFG_H */
