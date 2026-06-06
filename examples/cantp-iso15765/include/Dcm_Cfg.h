/*
 * Minimal stub of Dcm_Cfg.h for the cantp-iso15765 example.
 *
 * Upstream's PduR generator (vendor/as/tools/generator/PduR.py:100-101)
 * unconditionally emits `#include "Dcm_Cfg.h"` when any PduR routine
 * touches the `Dcm` module, and the generated PduR_Cfg.c references
 * `DCM_<routine_name>` identifiers in its routing table. Providing a
 * tiny header with those two macros is enough to compile the
 * generated config without pulling in the full upstream Dcm config
 * tree (Dem, NvM, OS tables, etc.).
 *
 * Used only by `examples/cantp-iso15765` and the functional Dcm sink
 * (`tests/functional/node/node_tp_sink.c`). Picked up by the L1
 * compile pipeline because `include_dirs_for` (backend/gen/compile.py)
 * scans every `include/` directory inside the staged project tree.
 */
#ifndef DCM_CFG_H
#define DCM_CFG_H

#include "Std_Types.h"

#define DCM_ISO_TP_RX 0u
#define DCM_ISO_TP_TX 0u

#endif /* DCM_CFG_H */
