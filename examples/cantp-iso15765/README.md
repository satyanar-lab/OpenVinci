# cantp-iso15765 — minimal ISO-15765 CanTp project

A small CanTp-only project used to exercise the segmented-transfer
runtime end-to-end. Unlike `com-minimal` (signals through Com) and
`canfd-minimal` (FD-sized PDUs), this one drives **a single CanTp
channel** that segments / reassembles SDUs longer than 8 bytes per the
ISO-15765 protocol (SF / FF / FC / CF frames).

What the config wires:

- A CanTp channel `ISO_TP` with classic-CAN `LL_DL=8` (so any SDU >7
  bytes forces multi-frame: FF + FC + CFs), `BS=0` (no further FC
  during a transfer), `STmin=0` (no separation time required).
- CanIf PDUs `ISO_TP_RX` (id `0x7e0`) and `ISO_TP_TX` (id `0x7e8`)
  with `up: "CanTp"` so CanIf delivers / accepts CanTp's wire frames
  directly (no PduR hop for that edge — CanIf.py emits
  `CanTp_RxIndication` / `CanTp_TxConfirmation` as the callbacks).
- PduR routes that take the reassembled SDU from CanTp to the
  diagnostic upper layer (`Dcm`) and back. We use the `Dcm` module
  name because upstream's PduR generator hardcodes the upper-layer
  API binding by name; `vendor/as/tools/generator/PduR.py:108-117`
  emits `PduR_DcmApi = { Dcm_StartOfReception, Dcm_CopyRxData, ... }`.
  The functional test ships a tiny sink that implements those symbols
  (see `tests/functional/node/node_tp_sink.c`) — the sink only buffers
  the reassembled SDU; segmentation lives entirely in upstream
  `CanTp.c`.

No Com module: this project intentionally doesn't include Com. CanTp
runs above CanIf and below Dcm directly, which is the simplest
faithful shape for a diagnostic transport.

## Why no PduR `CanIf ↔ CanTp` route

Upstream `CanIf.py` (line 124-127) emits `CanTp_RxIndication` /
`CanTp_TxConfirmation` directly into the CanIf PDU table when
`up: "CanTp"`. PduR isn't on that path. The PduR routes in this
project carry only the upper edge (`CanTp ↔ Dcm`), matching the
pattern in `vendor/as/app/app/config/Com/PduR.json:3-13`.

## Used by

- `backend/tests/test_gen_pipeline.py::test_cantp_iso15765_compiles_clean`
  — L1 generate + compile-check.
- `tests/functional/test_loopback.py::TestCanTpLoopback`
  — L2 end-to-end segmented transfer, byte-exact reassembly.
- `tests/golden/test_golden.py` — L3 byte-stable snapshot.
