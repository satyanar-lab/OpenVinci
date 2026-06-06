/*
 * OpenVinci minimal CanTp (ISO-15765) node — VERIFICATION LEVEL 2 (TP).
 *
 * Third in the family of functional nodes (after node_main.c for
 * classic Com and node_fd_main.c for FD-sized PDUs). This one
 * exercises upstream CanTp.c's segmented-transfer path end-to-end:
 *
 *   - CanIf delivers raw CAN frames at id 0x7E0 directly to
 *     CanTp_RxIndication (the CanIf RxPdu has up: "CanTp",
 *     see vendor/as/tools/generator/CanIf.py:124-127).
 *   - CanTp parses the N_PCI byte, reassembles SF / FF+FC+CFs into a
 *     single SDU, and hands it up via PduR_CanTpRxIndication →
 *     PduR_TpRxIndication → Dcm_TpRxIndication.
 *   - The Dcm sink (node_tp_sink.c) buffers the reassembled bytes and
 *     prints them as the harness expects.
 *
 * Init order mirrors `vendor/as/app/bootloader/main.c:122-149` for
 * the (Can, CanIf, CanTp, Dcm) subset — Com / NM / SecOC are not
 * present so there's no IpduGroupStart to call.
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
#include "CanTp.h"
#include "PduR.h"

extern Can_ConfigType Can_Config;
extern void Can_ReConfig(uint8_t Controller, const char *device, int port,
                         uint32_t baudrate);

static int parse_args(int argc, char *argv[], int *bus) {
  *bus = 0;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--bus") && i + 1 < argc) {
      *bus = atoi(argv[i + 1]);
      i++;
    }
  }
  return 0;
}

int main(int argc, char *argv[]) {
  int bus;
  parse_args(argc, argv, &bus);

  /* TCP simulator backend — same choice as the other two nodes. */
  Can_ReConfig(0, "simulator", bus, 500000);

  Can_Init(&Can_Config);
  CanIf_Init(NULL);
  PduR_Init(NULL);
  CanTp_Init(NULL);

  (void)CanIf_SetControllerMode(0, CAN_CS_STARTED);
  (void)CanIf_SetPduMode(0, CANIF_ONLINE);

  /* Warmup: let the simulator Can driver land its TCP socket before
   * we tell the harness "up." */
  for (int i = 0; i < 100; i++) {
    Can_MainFunction_Write();
    Can_MainFunction_Read();
    CanIf_MainFunction();
    CanTp_MainFunction();
    usleep(1000);
  }
  fprintf(stderr, "openvinci-node: tp bus=%d up.\n", bus);
  fflush(stderr);

  while (1) {
    /* Same per-tick pump order vendor/as's EcuM_Cfg uses for the
     * (Can, CanIf, CanTp) chain. std_timer drives CanTp's N_As /
     * N_Bs / N_Cr alarms internally; we just need to call the main
     * function on a regular cadence. */
    Can_MainFunction_Write();
    Can_MainFunction_Read();
    CanIf_MainFunction();
    CanTp_MainFunction();

    usleep(1000); /* 1 ms tick */
  }
  return 0;
}
