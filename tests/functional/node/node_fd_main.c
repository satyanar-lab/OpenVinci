/*
 * OpenVinci minimal CAN-FD COM-stack node — VERIFICATION LEVEL 2 (FD).
 *
 * Sister of node_main.c. Same init sequence and main-loop shape; the
 * only differences are:
 *
 *   - The Tx/Rx signals are 16-byte UINT8N (vs 1-byte INT8 in
 *     com-minimal), matching examples/canfd-minimal/config/Com/Com.json.
 *   - Default mode writes a known 16-byte payload via
 *     Com_SendSignal(COM_SID_TxFdSignal, …) every ~100 ms. The Com
 *     IPDU is configured with dlc=16, so the wire frame the broker
 *     sees has dlc=16 — the byte-exact FD-routing proof the harness
 *     asserts on. The bytes are constant across re-sends so the test
 *     can match exactly.
 *   - --probe mode prints "RxFdSignal=<32 hex chars>" whenever
 *     Com_ReceiveSignal(COM_SID_RxFdSignal, …) returns a buffer that
 *     differs from the previous read. The 16-byte buffer is whatever
 *     CanIf → PduR → Com decoded out of the 16-byte FD frame the
 *     harness injected — nothing is hardcoded or echoed back.
 *
 * `--bus N` sets the CAN bus index (TCP port 8000+N for the broker).
 */

#include <getopt.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "Std_Types.h"
#include "Can.h"
#include "CanIf.h"
#include "Com.h"
#include "Com_Cfg.h"
#include "PduR.h"

extern Can_ConfigType Can_Config;
extern void Can_ReConfig(uint8_t Controller, const char *device, int port,
                         uint32_t baudrate);

#define FD_PAYLOAD_BYTES 16

/* Sixteen distinct, non-zero bytes — distinguishable from any
 * uninitialised Com_PduData buffer and from the 0x00-fill Com's
 * zero-init Rx buffer would return before the first frame arrives. */
static const uint8_t k_tx_payload[FD_PAYLOAD_BYTES] = {
  0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
  0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f, 0x50, 0x51,
};

static int parse_args(int argc, char *argv[], int *bus, int *probe) {
  *bus = 0;
  *probe = 0;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--bus") && i + 1 < argc) {
      *bus = atoi(argv[i + 1]);
      i++;
    } else if (!strcmp(argv[i], "--probe")) {
      *probe = 1;
    }
  }
  return 0;
}

int main(int argc, char *argv[]) {
  int bus, probe;
  parse_args(argc, argv, &bus, &probe);

  /* "simulator" (TCP) — the broker speaks TCP. Same choice as the
   * com-minimal node; see node_main.c for the simulator vs
   * simulator_v2 rationale. */
  Can_ReConfig(0, "simulator", bus, 500000);

  Can_Init(&Can_Config);
  CanIf_Init(NULL);
  PduR_Init(NULL);
  Com_Init(NULL);

  (void)CanIf_SetControllerMode(0, CAN_CS_STARTED);
  (void)CanIf_SetPduMode(0, CANIF_ONLINE);
  Com_IpduGroupStart(0, TRUE);

  uint8_t tx_buf[FD_PAYLOAD_BYTES];
  uint8_t rx_buf[FD_PAYLOAD_BYTES];
  uint8_t rx_buf_last[FD_PAYLOAD_BYTES];
  memcpy(tx_buf, k_tx_payload, FD_PAYLOAD_BYTES);
  memset(rx_buf_last, 0, FD_PAYLOAD_BYTES);

  int ticks_until_send = 0;

  /* Warmup so the simulator Can driver lands its TCP socket on the
   * broker before the test asserts liveness. Same shape as the
   * com-minimal node. */
  for (int i = 0; i < 100; i++) {
    Can_MainFunction_Write();
    Can_MainFunction_Read();
    CanIf_MainFunction();
    usleep(1000);
  }
  fprintf(stderr, "openvinci-node: probe=%d bus=%d up.\n", probe, bus);
  fflush(stderr);

  while (1) {
    Can_MainFunction_Write();
    Can_MainFunction_Read();
    CanIf_MainFunction();
    Com_MainFunctionRx();
    Com_MainFunctionTx();

    if (!probe) {
      /* Default: write a constant 16-byte payload via Com so the FD
       * IPDU is assembled and Com_MainFunctionTx emits a frame at id
       * 0x200 with dlc=16 on the broker's wire format. */
      if (ticks_until_send == 0) {
        (void)Com_SendSignal(COM_SID_TxFdSignal, tx_buf);
        ticks_until_send = 100; /* re-arm every ~100 ms */
      } else {
        ticks_until_send--;
      }
    } else {
      /* Probe: print the 16-byte value Com_ReceiveSignal hands back as
       * soon as it changes (i.e., once the harness has injected a
       * frame and the CanIf→PduR→Com path has populated the Rx
       * buffer). The value comes from Com — not the raw frame bytes,
       * not a stub. */
      if (E_OK == Com_ReceiveSignal(COM_SID_RxFdSignal, rx_buf)) {
        if (memcmp(rx_buf, rx_buf_last, FD_PAYLOAD_BYTES) != 0) {
          printf("RxFdSignal=");
          for (int i = 0; i < FD_PAYLOAD_BYTES; i++) {
            printf("%02x", rx_buf[i]);
          }
          printf("\n");
          fflush(stdout);
          memcpy(rx_buf_last, rx_buf, FD_PAYLOAD_BYTES);
        }
      }
    }

    usleep(1000); /* 1 ms tick */
  }
  return 0;
}
