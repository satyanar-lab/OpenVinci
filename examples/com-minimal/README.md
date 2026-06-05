# com-minimal — minimal generate+compile fixture

A small COM-stack project authored specifically to exercise the
generation+compile pipeline. Unlike `canapp-min` (which mirrors the
real `vendor/as/app/app/config/` and pulls in SecOC / NM / Xcp / DBC
ancillary files), this one is the smallest possible project that:

- declares Com messages inline (no DBC),
- routes them directly from Com to CanIf via PduR (no SecOC wrapper),
- doesn't reference any module the engine doesn't yet model.

That is the configuration where the upstream generators produce
`Com_Cfg.{h,c}`, `CanIf_Cfg.{h,c}`, and `PduR_Cfg.{h,c}` that compile
cleanly against the BSW headers in `vendor/as/infras/communication/`
with `gcc -c -fsyntax-only`.

Used by the `backend/tests/test_gen_pipeline.py` end-to-end test.

## Naming convention

PduR routine `name`, CanIf PDU `name`, and the matching Com message's
network-prefixed macro must line up — PduR's generated C says
`COM_<routine_name>` and `CANIF_<routine_name>`, while Com generates
`COM_<network>_<message>`. Hence routines / CanIf PDUs are named
`CAN0_TX_MSG` / `CAN0_RX_MSG` here.
