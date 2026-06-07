# examples/h7-loopback

Single-node Com → CanIf → CAN config where the TX message and the RX
message share the **same CAN id (0x100)**. Built specifically for the
STM32H753ZI bring-up firmware in `hardware/stm32h753zi/`, which runs
FDCAN1 in **internal loopback** mode — every byte transmitted is
delivered straight back to the same controller's Rx FIFO.

Without a matching Rx PDU on the looped-back id, the OpenVinci CanIf
config would silently drop the looped frame (its lookup table is keyed
on canid). This example wires the id both ways so the loopback path
actually traverses CanIf → PduR → Com on receive.

Same shape as `examples/com-minimal` otherwise (single 8-bit signal in
each direction; 500 kbit/s; cyclic 1 s transmit).

See `hardware/stm32h753zi/README.md` for the on-board test recipe.
