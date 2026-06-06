/*
 * Honest Dcm upper-layer sink for the CanTp-segmented loopback test.
 *
 * Implements the PduR TP upper-layer API that upstream's PduR
 * generator emits routes against when `to: "Dcm"` appears in a route
 * (vendor/as/tools/generator/PduR.py:108-117):
 *
 *   Dcm_StartOfReception   — allocate / size the sink buffer
 *   Dcm_CopyRxData         — append a chunk to the buffer
 *   Dcm_TpRxIndication     — finalize and print the reassembled SDU
 *   Dcm_CopyTxData         — Tx is not exercised; refuses cleanly
 *   Dcm_TpTxConfirmation   — Tx is not exercised; no-op
 *
 * HARD RULE (PROMPT 4): the sink does NOT implement ISO-15765
 * segmentation. It does nothing more than memcpy the bytes upstream
 * CanTp.c hands it into a flat buffer and print the result on
 * TpRxIndication(E_OK). All SF/FF/FC/CF handling lives in the
 * upstream `CanTp.c` we're linking.
 *
 * Print format: `DcmRx[N]=<hex bytes>` where N is the SDU length the
 * CanTp layer reported via StartOfReception and the bytes are
 * whatever CopyRxData copied in. Matched by
 * TestCanTpLoopback in tests/functional/test_loopback.py.
 */

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "Std_Types.h"
#include "ComStack_Types.h"

/* 4 KiB ceiling matches PDU_LENGTH_MAX upstream CanTp.c clamps to;
 * any test SDU bigger than this would be rejected at the FF stage by
 * upstream CanTp itself (CanTp.c:315), not by the sink. */
#define DCM_SINK_BUFFER_BYTES 4096u

static uint8_t s_rx_buf[DCM_SINK_BUFFER_BYTES];
static PduLengthType s_rx_total;
static PduLengthType s_rx_offset;

BufReq_ReturnType Dcm_StartOfReception(PduIdType id, const PduInfoType *info,
                                       PduLengthType TpSduLength,
                                       PduLengthType *bufferSizePtr) {
  (void)id;
  (void)info;
  if (TpSduLength > DCM_SINK_BUFFER_BYTES) {
    return BUFREQ_E_OVFL;
  }
  s_rx_total = TpSduLength;
  s_rx_offset = 0u;
  *bufferSizePtr = DCM_SINK_BUFFER_BYTES;
  return BUFREQ_OK;
}

BufReq_ReturnType Dcm_CopyRxData(PduIdType id, const PduInfoType *info,
                                 PduLengthType *bufferSizePtr) {
  (void)id;
  if ((s_rx_offset + info->SduLength) > DCM_SINK_BUFFER_BYTES) {
    return BUFREQ_E_OVFL;
  }
  (void)memcpy(s_rx_buf + s_rx_offset, info->SduDataPtr, info->SduLength);
  s_rx_offset += info->SduLength;
  *bufferSizePtr = DCM_SINK_BUFFER_BYTES - s_rx_offset;
  return BUFREQ_OK;
}

void Dcm_TpRxIndication(PduIdType id, Std_ReturnType result) {
  (void)id;
  if (E_OK == result) {
    /* s_rx_offset == s_rx_total iff upstream CanTp fed us every byte
     * it reassembled. Print the actual reassembled length so the
     * harness can assert both length and content match. */
    printf("DcmRx[%u]=", (unsigned)s_rx_offset);
    for (PduLengthType i = 0; i < s_rx_offset; i++) {
      printf("%02x", s_rx_buf[i]);
    }
    printf("\n");
    fflush(stdout);
  } else {
    printf("DcmRx[err]\n");
    fflush(stdout);
  }
  s_rx_total = 0;
  s_rx_offset = 0;
}

BufReq_ReturnType Dcm_CopyTxData(PduIdType id, const PduInfoType *info,
                                 const RetryInfoType *retry,
                                 PduLengthType *availableDataPtr) {
  (void)id;
  (void)info;
  (void)retry;
  (void)availableDataPtr;
  return BUFREQ_E_NOT_OK;
}

void Dcm_TpTxConfirmation(PduIdType id, Std_ReturnType result) {
  (void)id;
  (void)result;
}
