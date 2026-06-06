# CAN FD feasibility (investigation, no code change)

**Scope.** Does an FD-sized PDU (>8 up to 64 bytes) route end-to-end
through the layers OpenVinci generates and the upstream BSW it links
against, on the host simulator? This document audits each layer with
file:line evidence and lists what would have to change. **It changes
nothing.**

## 1. The boundary, stated up front

CAN FD has two independent dimensions:

1. **FD-sized payloads** — DLC>8 PDUs (12, 16, 20, 24, 32, 48, 64
   bytes) and the framing rules that go with them (SF/FF/CF formats,
   STmin, the CanTp `LL_DL` byte).
2. **FD-bit-rate / BRS / data-phase timing** — the physical layer
   parameters (arbitration phase, data phase, sample-point split,
   bit-rate switch).

OpenVinci configures the **first** dimension. It does **not**
configure the second.

The second dimension lives in `Can_Cfg.{h,c}`, which is **hand-written
upstream** — `vendor/as/tools/generator/__init__.py:__GEN__` has no
`"Can"` entry (confirmed in `docs/AUTOAS_NOTES.md` §1.2), and the
sample `vendor/as/app/platform/simulator/src/config/Can_Cfg.c:21-77`
hardcodes `baudrate = 500000` per controller with no FD-specific
fields. The runtime struct
`vendor/as/infras/mcal/Can/Can_Priv.h:54` has a single
`uint32_t baudrate` and no `dataBaudrate` / `BRS` / sample-point-split
fields. The host simulator uses TCP (`simulator`) or UDP multicast
(`simulator_v2`); neither models a physical CAN bus, so BRS is
meaningless on this path anyway.

**Conclusion**: in OpenVinci's surface area, "FD support" can only
mean **FD-sized PDU routing on the host simulator** (and on real
targets, given a correctly-written `Can_Cfg.c`). BRS/data-phase
timing is out of scope by construction.

## 2. Per-layer findings

### 2.1 Broker (`can_simulator.c`) — TCP wire layer

**FD-clean.**

- `vendor/as/tools/libraries/Can/utils/can_simulator.c:19` — `#define CAN_MAX_DLEN 64 /* 64 for CANFD */`.
- `:54` — `struct can_frame { uint8_t data[CAN_MAX_DLEN + 5]; }`. Frame size on the wire is fixed 69 bytes regardless of DLC; bytes 0..63 are payload, 64..67 are big-endian canid, 68 is dlc.
- `:230-247` — `try_recv_forward` reads exactly `CAN_MTU` (69 bytes) per peer and forwards exactly `CAN_MTU` to every other peer with no dlc-based truncation.

The broker transports any DLC 0..64 byte-exact between peers. No change needed.

### 2.2 Simulator Can driver (`simulator_can.cpp`) — TCP client side

**FD-clean.**

- `vendor/as/tools/libraries/Can/src/simulator_can.cpp:19` — same `CAN_MAX_DLEN 64`.
- `:153-167` — `socket_write` asserts `dlc <= CAN_MAX_DLEN` (== 64) and `memcpy(frame.data, data, dlc)` before sending the fixed-size frame. Up to 64 bytes are honored.
- `:190-205` — `rx_notifiy` receives 69 bytes then calls `rx_notification(busid, mCANID(frame), mCANDLC(frame), frame.data, 0)` — passes the dlc value and the full 64-byte buffer pointer through unmodified.

### 2.3 Simulator platform Can.cpp (the MCAL → driver glue)

**FD-clean.**

- `vendor/as/app/platform/simulator/src/Can.cpp:40-45` — `struct CanFrame { … uint8_t data[64]; }`.
- `:192-219` — `Can_Write(Hth, PduInfo)` calls `can_write(busid, PduInfo->id, PduInfo->length, PduInfo->sdu)` with no clamp on `PduInfo->length`.
- `:266-319` — `Can_MainFunction_ReadChannelById` declares `uint8_t data[64]` and sets `dlc = sizeof(data)` (=64) before `can_read`. The received dlc and 64-byte buffer are handed to `CanIf_RxIndication` via `PduInfoType{SduDataPtr=data, SduLength=dlc}`.

### 2.4 MCAL Can.c (`infras/mcal/Can/Can.c`)

**FD-clean — no width assumption.** It only manages controller state
transitions and calls into the device ops; it never inspects payload
length.

- `vendor/as/infras/include/Can_GeneralTypes.h:57-62` — `Can_PduType { uint8_t *sdu; Can_IdType id; PduIdType swPduHandle; uint8_t length; }`. `length` is `uint8_t` so it carries 0..255 — fits FD's 0..64 cleanly.
- `:43-44` — defines `CAN_CAN_ID_TYPE 0x00000000u` and `CAN_CANFD_ID_TYPE 0x40000000u`. **Upstream's contract for marking a frame as FD is the top bits of `Can_IdType`.** Nothing below CanIf reads this bit; on the simulator path the broker only carries the 29 low bits (`mCANID` strips it during routing), so the FD bit is effectively informational on the host sim. On real targets the MCAL is responsible for honoring it.

### 2.5 CanIf runtime (`infras/communication/CanIf/CanIf.c`)

**FD-clean given correct config knobs.**

- `:38-46` — internal Rx/Tx packet pools use `CANIF_RX_PACKET_DATA_SIZE` / `CANIF_TX_PACKET_DATA_SIZE`. These default to **64** in `CanIf.py:61, 64` and in `CanIf_Priv.h:31-37` — so an enabled pool fits FD-sized PDUs. If a user overrode these to 8, FD would be silently dropped (`:367, :431` check `SduLength <= …_PACKET_DATA_SIZE`).
- `:71-159` — `CanIf_RxDispatch`: routes by `canid & CAN_CANID_MASK` (29-bit, strips the FD bit) — fine. The Rx call is just forwarded with `PduInfoPtr` unchanged; `SduLength` (`PduLengthType = uint32_t`, `ComStack_Types.h:22`) carries up to 4 GiB so 64 is trivial.
- `:161-220` — `CanIf_TransmitInternal`: assigns `canPdu.length = PduInfoPtr->SduLength`. `canPdu.length` is `uint8_t` so any value 0..255 fits. **The FD bit on `Can_IdType` is NOT propagated** — the canid field stored at config time (`txPdu->canid`) is whatever the generator wrote, and the generator strips it (see §2.6).

### 2.6 CanIf generator (`tools/generator/CanIf.py`)

**This is the first OpenVinci-visible gap.**

- `:115-118, :134-135, :253-254` — every canid stored or sorted is masked with `& 0x1FFFFFFF`. **The CAN-FD flag (`0x40000000`) is unconditionally stripped.** Even if the JSON had an FD-marked id, the generated `CanIf_Cfg.c` would emit it as Classic.
- This generator does not look at any FD field. There is no `"fd"` / `"FD"` per-PDU knob; no support for emitting `CAN_CANFD_ID_TYPE` flag.

**No length assumption in CanIf.py — it doesn't carry PDU length at all.** The CanIf table only has `(canid, mask, hoh, ControllerId, callbacks)`. Length flows separately through `Can_PduType.length` at transmit time, from the Com / CanTp configs.

### 2.7 Com runtime (`infras/communication/Com/Com.c`)

**FD-clean.**

- `vendor/as/infras/communication/Com/Com_Priv.h:70` — `typedef uint16_t Com_DataLengthType`; `:185` — IPdu `length` field is `Com_DataLengthType`. Range 0..65535 supports FD's max 64.
- Tx path: `Com.c:569-573, :849-907` — assembles `PduInfo.SduLength = IPduConfig->length` (the per-IPDU configured size) then hands to PduR. Tx buffer is `Com_PduData_*[length]` allocated in the generated `Com_Cfg.c` to exactly `msg["dlc"]` bytes (see §2.8).
- Rx path: `:612-635, :667-714, :935-1016` — `memcpy(IPduConfig->ptr, …, dynLen)` where `dynLen <= IPduConfig->length`. No 8-byte clamp anywhere.

### 2.8 Com generator (`tools/generator/Com.py`)

**FD-clean — `dlc` is plumbed through unchanged.**

- `:513` — `static uint8_t Com_PduData_%s[%s]` uses `msg["dlc"]` verbatim. A `dlc=64` JSON produces a 64-byte buffer.
- `:259` — IPdu config `length` is `sizeof(Com_PduData_*)` (== `dlc`).
- `:528` — dynamic length: `Com_DataLengthType %s_dynLen = %s` uses configured dlc; type is uint16, no clamp.
- No `"fd"` flag. The generator does not emit FD framing or BRS hints; it does not need to — that's the MCAL's domain.

**Caveat.** The fallback Tx macro `COM_TX_FOR_<net>` at `Com.py:320-322` writes `dlPdu.id = 0x%X` straight from `msg["id"]` — without the FD bit. This macro is only used if `USE_PDUR` is undefined (a Com-talks-directly-to-Can path). Our generated stack uses PduR (CanIf), so this macro is dead in the test loopback. Still: the FD bit is dropped there too, consistent with §2.6.

### 2.9 PduR generator (`tools/generator/PduR.py`)

**FD-clean — PduR generator carries no length, no width.** Routing is by `(srcModule, srcHandle) → [(dstModule, dstHandle, api)]`. No clamp, no FD assumption.

### 2.10 CanTp.c — FD already first-class

CanTp is the most FD-aware layer in the upstream stack.

- `vendor/as/infras/communication/CanTp/CanTp.c:87-100` — `CanTp_GetDL(len, LL_DL)` selects from `{8, 12, 16, 20, 24, 32, 48}` (and falls through to LL_DL itself, typically 64). Exactly the FD DLC set.
- `:102-118` — `CanTp_GetSFMaxLen`: SF format branches on `config->LL_DL > 8u`. For LL_DL>8 the SF has a 2-byte PCI (the "FD escape" `00 XX` where XX is the length byte).
- `:145-199` — `CanTp_HandleSF`: implements the FD-escape SF format when `LL_DL > 8`.
- `:294-301, :594, :616-626, :683-698` — all FF/CF assembly is `LL_DL`-aware: padding to next valid FD frame size, FF len up to `0xFFF` (Classic) or wider (FD), CF tail padding.
- `:923-959` — RxIndication validates frame width against `config->LL_DL`.

In short, FD diagnostic transport works upstream **iff** the user sets per-channel `LL_DL` to a value > 8.

### 2.11 CanTp generator (`tools/generator/CanTp.py`)

**Already exposes the FD knob.**

- `:61-62, :76, :101` — `chl["LL_DL"]` flows through to `static uint8_t u8<chl>Data[LL_DL]` and `.LL_DL = LL_DL` in `CanTpChannelConfigs[]`. Default 8 (Classic). Setting it to 64 in JSON is sufficient.
- `:117-122` — there is even a runtime override: `getenv("LL_DL")` patches the channel at startup. (Don't rely on this for production tests; it overrides *every* channel.)

### 2.12 DBC importer (`backend/importer/dbc.py`) — OpenVinci side

**Passes `dlc` through verbatim, FD bit handling is missing.**

- `:45` — `"dlc": msg.length` — `cantools` reports message length in bytes, and cantools does parse CAN FD `BO_` lines (it recognizes DLC values >8 from FD DBCs). So an FD DBC produces `dlc=64` in our import.
- No DBC importer code looks at `is_fd` / `fd_format` on cantools messages. cantools exposes `msg.is_fd` (we don't read it), so the FD flag from the DBC is dropped. The downstream effect: `CanIf.py:115` strips the FD bit anyway, so even if we surfaced it, the upstream generator wouldn't emit it.

### 2.13 OpenVinci JSON Schemas (`model/`)

**Already FD-shaped on Com side; FD bit absent on CanIf/Com message side.**

- `model/com.schema.json:93` — `"dlc": { "type": "integer", "minimum": 0, "maximum": 64 }`. Schema accepts FD-sized messages today.
- `model/cantp.schema.json:44-49` — `LL_DL` enum `[8, 12, 16, 20, 24, 32, 48, 64]` with FD-explicit description. Schema is FD-ready.
- `model/shared/types.schema.json:46-49` — `NetworkKind` enum is `["CAN", "CANFD", "LIN"]`. The discriminator exists but is currently unused — no rule lifts `"CANFD"` into any code-gen branch, and no engine rule cross-checks `dlc>8` against `network == "CANFD"`.
- **No FD bit on Com messages.** There is no `"fd": true` or `"frameFormat": "CANFD"` per-message field in `model/com.schema.json` or in CanIf PDU entries.

## 3. Verdict — what works today vs what does not

| Path | Today | Why |
|------|-------|-----|
| `Com_SendSignal` of a 64-byte IPDU → broker → another peer | **Works on the host simulator** (TCP) | All buffers and length fields along the data path are already wide enough (§2.1–§2.5, §2.7–§2.10). The Tx leg requires no FD bit on the host sim because the broker doesn't model the physical layer. |
| Same, with the FD bit set on the wire on real hardware | **Does not work** | `CanIf.py:115, :134-135, :253-254` strips `0x40000000`. The MCAL on a real ECU would emit a Classic frame at the same canid. |
| `CanTp` segmented transfer with FD framing (LL_DL=64) | **Works upstream** if the user authors a CanTp JSON with `LL_DL=64`; OpenVinci's schema already allows this. | §2.10, §2.11, §2.13. |
| DBC importer producing FD-marked PDUs | **Does not** preserve FD bit | `dbc.py:45` only reads `msg.length`, never `msg.is_fd`. We'd be importing FD-sized PDUs as Classic. |
| Engine rule "dlc>8 ⇒ network must be CANFD" | **Does not exist** | The `NetworkKind` enum is just a string. |

## 4. What would have to change

### 4.1 In OpenVinci code (this repo)

Listed in dependency order — do **not** treat this as a TODO; it is the minimum change-set if FD-PDU routing becomes a goal.

1. **`backend/importer/dbc.py:45`** — also propagate the FD flag:
   ```python
   "dlc": msg.length,
   "fd": bool(getattr(msg, "is_fd", False)),
   ```
   (cantools sets `is_fd` from the DBC's `BO_` flags / `VFrameFormat` attribute.)

2. **`model/com.schema.json` message $def** — add `"fd": { "type": "boolean", "default": false }`. Add a `dependentSchemas` clause: `{ "fd": { "properties": { "dlc": { "minimum": 0, "maximum": 64 } } } }` (already 64 by default, but make the linkage explicit).

3. **Engine cross-rule** (new file under `backend/engine/`):
   - `dlc > 8` ⇒ require Com network to be on a CANFD-capable network *or* warn. The current `network == "CAN"` is ambiguous about FD; `NetworkKind` was added for exactly this.
   - `msg.fd == True` ⇒ require the corresponding CanIf PDU + CanTp channel (if any) to carry the FD flag through.

4. **`backend/gen/`** — when staging CanIf entries, OR the FD flag back into the canid (or carry it as a separate field if we want to keep our model JSON portable). This must be done after the upstream generator has run, or via a wrapper that doesn't fight `CanIf.py:115`'s mask. Practically: a post-generation rewrite of `CanIf_Cfg.c` to OR `CAN_CANFD_ID_TYPE` into the affected `txPdus[].canid` literals. This is the **invasive** part — we either patch the post-generated C or upstream a flag-aware `CanIf.py`.

5. **Optional: tests/functional**. A new `TestComStackFdLoopback` parameterized on `dlc ∈ {12, 24, 64}` that links the same node with a 64-byte Tx/Rx Com signal and asserts the broker forwards all 64 bytes byte-exact. The fixtures already build for FD; only the `examples/com-minimal` JSON and the `node_main.c` Tx/Rx byte selector would need a tweak.

### 4.2 In `vendor/as` (upstream)

If we want FD to round-trip on real CAN-FD hardware (not just the host
sim), one upstream change is required:

- **`vendor/as/tools/generator/CanIf.py:115, :134-135, :253-254`** — stop unconditionally masking the FD bit. The fix is roughly: replace `& 0x1FFFFFFF` with `& 0x5FFFFFFF` on every write path so `CAN_CANFD_ID_TYPE = 0x40000000` survives, and add a `"fd": true/false` knob with the same surface as the canid bit.

That change must come from `autoas/as` (per CLAUDE.md "Never patch
`vendor/as` from this repo"). Until it lands, FD-on-real-HW is gated.

### 4.3 What does NOT have to change (and confirmed against the code)

- Broker, simulator Can driver, MCAL Can.c, CanIf.c runtime, Com.c runtime, PduR.c, CanTp.c — all already FD-clean (§2.1–§2.5, §2.7, §2.10).
- Com.py generator — `msg["dlc"]` plumbing already produces a 64-byte buffer (§2.8).
- CanTp.py generator — `LL_DL` knob already exposed (§2.11).
- `model/com.schema.json` and `model/cantp.schema.json` — already accept FD sizes (§2.13). `NetworkKind` enum already lists `"CANFD"`.

## 5. Boundary restatement (and confirmation against the code)

OpenVinci's "FD support" can plausibly mean **FD-sized PDU routing on
the host simulator (and on real targets via a correctly hand-written
`Can_Cfg.c`)**. It cannot mean BRS / data-phase / bit-rate-switch
configuration, because:

- `vendor/as/infras/mcal/Can/Can_Priv.h:48-95` defines `Can_ChannelConfigType` with one `uint32_t baudrate` and *no* data-phase or BRS fields.
- `vendor/as/tools/generator/__init__.py:__GEN__` has no `"Can"` key (docs/AUTOAS_NOTES.md §1.2 confirms this) — the low-level CAN driver config is hand-authored C, not generated, and OpenVinci does not own that surface.
- The host simulator (`vendor/as/app/platform/simulator/src/Can.cpp`, `tools/libraries/Can/src/simulator_can.cpp`, `tools/libraries/Can/utils/can_simulator.c`) speaks TCP / UDP, not a physical CAN bus, so BRS would have no observable effect on the L2 loopback even if we did configure it.

If a real target ever links our generated `*_Cfg.c`, it will pair them
with a hand-written `Can_Cfg.c` that the integrator authored — and
that file is where BRS / data-baudrate / sample-point-split live.
That's the boundary, and the code above is exactly where it sits.
