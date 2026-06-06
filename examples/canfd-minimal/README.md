# canfd-minimal — minimal CAN FD generate+compile fixture

Sister of `examples/com-minimal`, but every PDU is CAN FD with a
16-byte payload. The minimal config that exercises:

- `Com.message.fd: true` on both Tx and Rx,
- `Com.message.dlc: 16` (>8, only legal because of `fd: true`),
- matching `CanIf.{Rx,Tx}Pdu.fd: true` so the intent survives at
  the CanIf table even though the upstream `CanIf.py` generator
  strips the FD bit from the canid itself (see
  `docs/CANFD_FEASIBILITY.md` §2.6).

The network kind is `"CAN"` (not `"CANFD"`) because the upstream
generator's `COM_TX_FOR_<net>` macro at `Com.py:320` only emits a body
for `network == "CAN"` (and skips for `"LIN"`); `"CANFD"` would trigger
a bare-`raise`. The FD flag belongs on the PDU regardless — that's
where the upstream BSW threads it (see `docs/CANFD_FEASIBILITY.md`
§2.4, §2.6) — so a CAN-typed network with per-PDU `fd: true` is the
correct scope.

Used by the schema-validation example tests
(`backend/tests/test_schemas_validate_examples.py`) and as a fixture
for the FD generate+compile coverage in
`backend/tests/test_gen_pipeline.py`.

## Why dlc=16 specifically

Smallest legal CAN FD size above 8 that exercises the
`Com_PduData_*[16]` buffer allocation (Com.py:513) and the FD-only
length branch in CanTp's SF format (CanTp.c:104) — though this example
doesn't include CanTp, just Com → PduR → CanIf. Equally valid choices
would be 12, 20, 24, 32, 48, or 64. Both messages use the same size to
keep the fixture symmetric.

## Naming convention

Identical to com-minimal — PduR routine `name`, CanIf PDU `name`, and
the matching Com message's network-prefixed macro line up:
`CAN0_TX_FD_MSG` / `CAN0_RX_FD_MSG`.
