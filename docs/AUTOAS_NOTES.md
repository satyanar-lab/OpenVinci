# AUTOAS_NOTES — Reverse-engineered facts about `autoas/as`

Source: `vendor/as/` (git submodule pointing at https://github.com/autoas/as).
Upstream license: **Dual GPLv3 / Commercial**, Copyright Parai Wang
(`vendor/as/LICENSE`). All paths below are inside the submodule unless noted.

Everything in this file is cited to specific files/lines in the submodule.
Nothing is invented: where the upstream does not document something, this
file says so.

---

## 1. Config format used by autoas/as

### 1.1 Overall model: one JSON file per BSW module, dispatched by `"class"`

Every config file is a plain JSON object whose top-level `"class"` key names
the BSW module. The generator factory dispatches on that key:

```
vendor/as/tools/generator/__init__.py:44-76
    __GEN__ = {
        "NvM": NvMGen, "RoD": RoDGen, "Dem": DemGen,
        "Com": ComGen, "Net": NetGen, "Factory": FactoryGen,
        "MemCluster": MCGen, "PduR": PduRGen,
        "CanTp": CanTpGen, "LinTp": LinTpGen, "CanIf": CanIfGen,
        "Rte": RteGen, "protoc": ProtocGen, "OS": OsGen,
        "Dcm": DcmGen, "Trace": TraceGen, "EcuC": DummyGen,
        "Xcp": XcpGen, "LinIf": LinIfGen, "J1939Tp": J1939TpGen,
        "CanNm": CanNmGen, "OsekNm": OsekNmGen, "Nm": NmGen,
        "CanSM": CanSMGen, "ComM": ComMGen, "Csm": CsmGen,
        "SecOC": SecOCGen, "E2E": E2EGen, "TLS": TLSGen,
        "Mirror": MirrorGen, "BL": BLGen,
    }
```

The `Generate(cfgs)` entry point at
`vendor/as/tools/generator/__init__.py:124` loads each JSON, looks up its
`"class"`, runs the matching generator, and writes outputs into a sibling
`GEN/` directory next to the JSON (see `Gen()` in each generator, e.g.
`vendor/as/tools/generator/Factory.py:106-111`).

There is **no upstream JSON Schema** for these files. The closest thing is
the PyQt5 GUI schema at `vendor/as/tools/json.editor/schema.json`
(1561 lines), which encodes property names, types, defaults, ranges, and
conditional visibility for the GUI. The schema uses non-standard extensions
(`enumref`, `enabled` expressions, `friends`, `map`) — see
`vendor/as/doc/EN/JsonEditor.md:36-43`.

The canonical example configs are under `vendor/as/app/app/config/`:

```
app/app/config/Com/Com.json        app/app/config/CanTp/CanTp.json
app/app/config/Com/CanIf.json      app/app/config/Dcm/Dcm.json
app/app/config/Com/PduR.json       app/app/config/NvM/NvM.json
app/app/config/Com/CanNm.json      app/app/config/SecOC/SecOC.json
app/app/config/Com/CanSM.json      app/app/config/E2E/E2E.json
app/app/config/Com/ComM.json       app/app/config/Xcp/Xcp.json
app/app/config/Com/Nm.json         app/app/config/Csm/Csm.json
app/app/config/Com/OsekNm.json     app/app/config/Mirror/Mirror.json
```

### 1.2 Per-module schemas (Can, CanIf, CanTp, PduR, Com)

#### Can (low-level driver)

There is **no `class: "Can"` JSON generator** in the upstream `__GEN__` map
(see §1.1). The Can driver config is a hand-written C file:
`app/platform/simulator/src/config/Can_Cfg.c`, registered as a library in
`app/platform/simulator/SConscript:5-10`:

```python
libsForSimulator = {
    "Can": Glob("src/config/Can_Cfg.c"),
    "Lin:as": Glob("src/config/Lin_Cfg.c"),
    ...
}
```

The simulator-flavour `Can.cpp` driver speaks to a TCP/UDP CAN broker on
`localhost` — see §3 below and `vendor/as/doc/CN/virtual-can-env.md`. Bit
timing and baudrate for the Com network are carried as fields on the **Com**
JSON (`device`, `port`, `baudrate`) — see §1.2.5.

#### CanIf (`class: "CanIf"`)

Reference doc: `vendor/as/doc/EN/CanIf.md`. Generator:
`vendor/as/tools/generator/CanIf.py`. GUI schema:
`vendor/as/tools/json.editor/schema.json:544-590`. Example:
`vendor/as/app/app/config/Com/CanIf.json`.

Top-level fields read by the generator
(`tools/generator/CanIf.py:26-71`):

| Field                 | Type     | Default | Meaning                          |
|-----------------------|----------|---------|----------------------------------|
| `RxPacketPoolSize`    | int      | 0       | `#define CANIF_RX_PACKET_POOL_SIZE` |
| `RxPacketDataSize`    | int      | 64      | `#define CANIF_RX_PACKET_DATA_SIZE` |
| `TxPacketPoolSize`    | int      | 0       | `#define CANIF_TX_PACKET_POOL_SIZE` |
| `TxPacketDataSize`    | int      | 64      | `#define CANIF_TX_PACKET_DATA_SIZE` |
| `MainFunctionPeriod`  | int (ms) | 10      | `#define CANIF_MAIN_FUNCTION_PERIOD`|
| `UsePostBuildConfig`  | bool     | false   | `#define CANIF_USE_PB_CONFIG`       |
| `UseTxCallout`        | bool     | false   | `#define CANIF_USE_TX_CALLOUT`      |
| `UseRxCallout`        | bool     | false   | `#define CANIF_USE_RX_CALLOUT`      |
| `networks[]`          | array    | —       | one entry per CAN controller        |

Each `networks[i]` object
(`tools/generator/CanIf.py:32-46`, `schema.json:546-589`):

| Field            | Type                 | Notes                                   |
|------------------|----------------------|-----------------------------------------|
| `name`           | string               | e.g. `"CAN0"` — also the CanIf channel  |
| `me`             | string               | Self node name in the DBC (default `AS`)|
| `dbc`            | path                 | DBC for Rx/Tx PDU autogeneration        |
| `use_dbc`        | bool                 | gates `dbc`/`ignore`                    |
| `TxTimeout`      | int (ms)             | default 100; non-zero enables `CANIF_USE_TX_TIMEOUT` |
| `NumHth`/`NumHrh`| int                  | hardware-object handle counts (mostly 1)|
| `ignore[]`       | string[]             | DBC frame names to drop                 |
| `RxPdus[]`       | array of PDU         | see below                               |
| `TxPdus[]`       | array of PDU         | see below                               |
| `E2E[]`          | string[]             | E2E-protected PDU names                 |

RxPdu / TxPdu object (`schema.json:562-587`):

| Field     | Type | Notes                                                  |
|-----------|------|--------------------------------------------------------|
| `name`    | str  | Unique across the whole config                         |
| `id`      | hex  | CAN ID                                                 |
| `hoh`     | int  | Hardware object handle (0..NumH{th,rh}-1)              |
| `mask`    | hex  | Optional acceptance mask (Rx only)                     |
| `dynamic` | bool | Tx-only: dynamic ID at runtime                         |
| `up`      | enum | Upper layer: one of `CanTp, OsekNm, CanNm, PduR, Com, Xcp, J1939Tp, CanTSyn, SecOC` or any `"User*"` name (`docs/EN/CanIf.md:78-100`) |

Generator outputs (per `tools/generator/CanIf.py`): `GEN/CanIf_Cfg.h` and
`GEN/CanIf_Cfg.c` next to the JSON. `#define CANIF_<PduName>` macros for
each Rx/Tx PDU; `#define CANIF_CHL_<NetName>` for each controller.

#### CanTp (`class: "CanTp"`)

Reference doc: `vendor/as/doc/EN/CanTp.md`. Generator:
`vendor/as/tools/generator/CanTp.py`. GUI schema:
`vendor/as/tools/json.editor/schema.json:650-673`. Example:
`vendor/as/app/app/config/CanTp/CanTp.json`.

Top-level fields:

| Field                 | Type | Default | Macro / effect                       |
|-----------------------|------|---------|--------------------------------------|
| `UseTxConfirmation`   | bool | true    | `CANTP_USE_TX_CONFIRMATION`          |
| `UsePostBuildConfig`  | bool | false   | `CANTP_USE_PB_CONFIG`                |
| `MainFunctionPeriod`  | int  | 10 ms   | `CANTP_MAIN_FUNCTION_PERIOD`         |
| `STMinAdjust`         | int  | 0       | `CANTP_STMIN_ADJUST`                 |
| `zero_cost`           | str  | —       | `PDUR_<X>_LINTP_ZERO_COST`           |
| `channels[]`          | arr  | —       | one entry per TP channel             |

Channel object (`tools/generator/CanTp.py:75-100`,
`schema.json:653-672`):

| Field             | Type     | Default     | Meaning |
|-------------------|----------|-------------|---------|
| `name`            | string   | —           | Macro suffix; matching CanIf PDUs must be `<name>_RX` / `<name>_TX` (CanTp.md:78-92) |
| `AddressingFormat`| enum     | `STANDARD`  | `STANDARD` or `EXTENDED` |
| `N_TA`            | hex      | 0           | required iff `EXTENDED`  |
| `N_As`            | int (ms) | 25          | tx frame time            |
| `N_Bs`            | int (ms) | 1000        | wait for FC              |
| `N_Cr`            | int (ms) | 1000        | wait for CF              |
| `STmin`           | int      | 0           | min CF separation        |
| `BS`              | int      | 8           | block size               |
| `WftMax`          | int      | 8           | max consecutive wait FCs |
| `LL_DL`           | int      | 8           | 8 = CAN, 64 = CAN FD     |
| `padding`         | int      | 0x55        | padding byte             |
| `ComType`         | enum     | `PHYSICAL`  | `PHYSICAL` or `FUNCTIONAL` (functional channels are Rx-only) |
| `RxPduId`/`TxPduId`| string  | `<name>_RX`/`_TX` | override PduR routine name |

Output: `GEN/CanTp_Cfg.h` + `GEN/CanTp_Cfg.c` (one `CanTp_ChannelConfigType`
entry per channel — struct definition in `docs/EN/CanTp.md:34-55`).

#### PduR (`class: "PduR"`)

Reference doc: `vendor/as/doc/EN/PduR.md`. Generator:
`vendor/as/tools/generator/PduR.py`. GUI schema:
`vendor/as/tools/json.editor/schema.json:609-648`. Example:
`vendor/as/app/app/config/Com/PduR.json`.

Top-level fields:

| Field        | Type  | Meaning                                                  |
|--------------|-------|----------------------------------------------------------|
| `routines[]` | array | Routing rules (see below)                                |
| `networks[]` | array | Bus contexts — `name`, `network` (`CAN`/`LIN`), `me`, `dbc`, `ignore[]` |
| `memory[]`   | array | Optional `MemCluster` for buffered TP gateway. Items: `{name,size,number}` — enables `PDUR_USE_MEMPOOL` (`tools/generator/PduR.py:57-80`) |

Routine object (`tools/generator/PduR.py:25-50`, schema:611-619):

| Field            | Type   | Notes                                            |
|------------------|--------|--------------------------------------------------|
| `name`           | string | PDU name (also `CANIF_<name>`/`PDUR_<name>` macro)|
| `from`           | enum   | Source module                                    |
| `to`             | enum   | Destination module                               |
| `dest`           | string | Optional rename at destination                   |
| `fake`           | string | Optional alias macro                             |
| `destinations[]` | array  | Multi-destination fan-out: `[{name,to,fake?}]`   |

Module enum for `from`/`to` (schema:616-617): `CanIf, CanTp, OsekNm, CanNm,
PduR, Dcm, Com, LinTp, DoIP, J1939Tp`. Generator also accepts `SecOC` and
`Mirror` (see example `app/app/config/Com/PduR.json`). TP↔TP routes
auto-enable `PDUR_USE_TP_GATEWAY` (`PduR.py:49-60`).

Limitation called out in `docs/EN/PduR.md:131-134`: no LinIf↔CanIf gateway.

#### Com (`class: "Com"`)

Reference doc: `vendor/as/doc/EN/Com.md`. Generator:
`vendor/as/tools/generator/Com.py` (912 lines — the largest). GUI schema:
`vendor/as/tools/json.editor/schema.json:715-…` (continues past line 739).
Example: `vendor/as/app/app/config/Com/Com.json`.

Top-level fields:

| Field             | Type        | Meaning                                                |
|-------------------|-------------|--------------------------------------------------------|
| `E2E`             | path        | Path to a sibling `E2E.json` (e.g. `"../E2E/E2E.json"`)|
| `nodes[]`         | string[]    | Enum source for per-signal `node`                       |
| `group_signals[]` | string[]    | Pre-declared group-signal names                         |
| `networks[]`      | array       | One entry per bus (see below)                           |

Network object (schema:720-739, example `app/app/config/Com/Com.json:5-42`):

| Field                            | Type   | Default     | Notes                              |
|----------------------------------|--------|-------------|------------------------------------|
| `name`                           | string | —           | e.g. `"CAN0"` (matches CanIf/PduR) |
| `network`                        | enum   | `CAN`       | `CAN`, `CANFD`, or `LIN`           |
| `device`                         | enum   | `simulator_v2` | `simulator_v2`, `peak`, `zlg`, `vxl` — sim-only |
| `port`                           | int    | 0           | hardware/bus index                 |
| `baudrate`                       | int    | 500000      | bits/sec                           |
| `me`                             | string | `AS`        | self node name (matches DBC sender)|
| `use_dbc`                        | bool   | false       | gates `dbc`                        |
| `dbc`                            | path   | —           | DBC file                           |
| `use_ldf` / `ldf`                | LIN    | —           | only when `network == "LIN"`       |
| `groups[]`                       | array  | —           | `[{<groupSignalName>: ["sig1",…]}]`|
| `trigger[]`                      | str[]  | —           | signals that trigger Tx            |
| `messages[]`                     | array  | —           | manual messages (in addition to DBC)|
| `enable_message_tx_callout`      | bool   | false       | per-msg Tx callout                 |
| `enable_message_rx_callout`      | bool   | false       | per-msg Rx callout                 |
| `enable_message_rx_notificaiton` | bool   | false       | (sic; spelling in upstream schema) |
| `enable_signal_rx_notification`  | bool   | false       | per-signal Rx notification         |
| `timeout_factor`                 | int    | 10          | timeout multiplier                 |
| `E2E[]`                          | array  | —           | per-PDU profile bindings           |

Message object (example `app/app/config/Com/Com.json:21-36`):
`{name, id (hex), dlc, node, CycleTime, signals:[ {name, start, size,
endian:"big"|"little", InitialValue, sign:"+"|"-", factor, offset, min, max,
node:[...] } ]}`. Signal Rx context fields handled by `gen_rx_sig_cfg`
include `InvalidNotification`, `RxNotification`, `RxTOut`, `FirstTimeout`,
`Timeout`, `DataInvalidAction`, `RxDataTimeoutAction` (`Com.py:11-42`).

Outputs: `GEN/Com_Cfg.h`, `GEN/Com_Cfg.c`, and an intermediate `GEN/Com.json`
that fuses DBC-derived messages with the manually declared ones
(`docs/EN/Com.md:41-46`).

### 1.3 Cross-file integrity rules (from the docs and example configs)

- A CanTp `channels[i].name` of `X` requires CanIf PDUs `X_RX` and `X_TX`
  with `up: "CanTp"` (`docs/EN/CanTp.md:78-92`).
- CanIf PDU `name` values must be unique across the whole config
  (`docs/EN/CanIf.md:42`).
- PduR routine `name` matches either a CanIf PDU (for `*_TX`/`*_RX` paths)
  or a Com PDU (for SDU↔TP routing) — see `app/app/config/Com/PduR.json` for
  worked examples.
- DBC referenced by CanIf/PduR/Com should contain only the COM messages;
  diag/NM/TP/XCP frames must be removed first (`docs/EN/CanIf.md:46-48`).

---

## 2. Code-generator commands (verified)

### 2.1 Via SCons (the upstream-blessed path)

The build system is **Python SCons**, root `vendor/as/SConstruct` (8 lines)
and `vendor/as/SConscript`. CLI options are registered in
`tools/building.py:17-45`:

```
--app=<AppName>      pick application (e.g. CanApp, CanSimulator, IsoTpSend)
--lib=<LibName>      pick library     (e.g. AsPy, AsOne, CanLib)
--cpl=<Compiler>     default GCC
--os=<OS>            optional RTOS (HostOS used on PC)
--gen                force regeneration of all configs
--prebuilt           use prebuilt libraries
--cfg=<dir>          override config root
--release=<cmake|make|build>
```

When you build a registered application via `scons --app=...`, the
application's `gencfg()` / `config()` calls `RegisterConfig(name,
[<json>...])` which internally calls `self.Generate(js)` →
`tools.building.generate()` → `generator.Generate()`
(`tools/building.py:1988-2014` and `:2596-2607`). That is, **the generators
run automatically whenever the build sees a `.json` source**. See the
worked example in `app/app/SConscript:44-100` (CanApp).

### 2.2 Standalone code generation (no SCons)

`generator.Generate(cfgs, force=False)` is importable from
`vendor/as/tools/`:

```sh
cd vendor/as
python -c "import sys; sys.path.append('tools'); \
           from generator import Generate; \
           Generate(['app/app/config/Com/Com.json',
                     'app/app/config/Com/CanIf.json',
                     'app/app/config/Com/PduR.json',
                     'app/app/config/CanTp/CanTp.json'], True)"
```

Outputs land in `app/app/config/<Module>/GEN/`. A `.gendb.pkl` cache at the
repo root records md5 hashes of JSON+DBC and skips regeneration when nothing
changed (`tools/generator/__init__.py:97-150`).

### 2.3 Via the PyQt5 JSON Editor GUI

```sh
cd vendor/as/tools/json.editor
python main.py                 # default SSAS schema
python main.py -s schema.json -c app/app/config/Com/Com.json
```

The editor (`json.editor/main.py`) renders the multi-module
`schema.json` and exposes a **Generate** menu action that writes the JSON
files and calls `generator.Generate(cfgs, True)`
(`json.editor/main.py:264-285`). DBC import/export plugins live in
`json.editor/plugin/{ImportDBC,ExportDBC}.py`.

---

## 3. Host/PC simulation target

### 3.1 What "host simulation" means in this repo

`app/platform/simulator/` is the Win/Linux platform shim. Its SConscript
(`app/platform/simulator/SConscript:13-30`) provides a `Simulator` library
with stub Can / Lin / Dio / Port drivers backed by IP sockets. Application
recipes in `app/app/SConscript` add `self.LIBS.append("Simulator")` when
building for PC (e.g. `ApplicationCanApp.platform_config`,
`app/app/SConscript:67-83`).

The CAN driver in `app/platform/simulator/src/Can.cpp` calls into
`canlib` (`tools/libraries/Can/include/canlib.h`) and talks to an
out-of-process broker. Supported devices (from `docs/CN/virtual-can-env.md`
and `schema.json:726`): `simulator` (TCP), `simulator_v2` (UDP multicast),
`qemu`, `vxl`, `peak`, `zlg`.

### 3.2 Toolchain prerequisites

Per `docs/EN/build-env-setup.md` (the upstream targets MSYS2 on Windows;
the same Python deps work on Linux):

```sh
# Python deps used everywhere
pip install scons pyserial pybind11 pillow ply pyqt5 bitarray
# (Windows-only extras come via MSYS2: gcc, qemu, protobuf, gtk3, etc.)
```

### 3.3 Build + run the CAN bus broker (CanBusSimulator)

The broker is `ApplicationCanSimulator` in
`tools/libraries/Can/SConscript:70-75`:

```sh
cd vendor/as
scons --app=CanSimulator
# Windows: build\nt\GCC\CanSimulator\CanSimulator.exe 0
# Linux:   build/posix/GCC/CanSimulator/CanSimulator 0
# the trailing "0" is the bus/port index
```

Output path is `build/<os>/<compiler>/<appName>/<appName>{.exe}` per
`tools/building.py:51-60, 643, 813`.

### 3.4 Build + run a sample COM stack app (CanApp)

`ApplicationCanApp` (`app/app/SConscript:65-104`) wires every module in
this doc (Com, CanIf, CanTp, PduR, CanNm, OsekNm, CanSM, ComM, Nm, Xcp,
StdTrace, Csm, SecOC, E2E, Mirror, Dcm, Dem, NvM) into one PC binary.

```sh
cd vendor/as
scons --app=CanApp
build/<os>/GCC/CanApp/CanApp        # Linux
build\nt\GCC\CanApp\CanApp.exe      # Windows
```

`build-env-setup.md:109-122` shows the same flow plus an `IsoTpSend`
tester that drives diagnostic requests against `CanApp` over the broker.

### 3.5 Other relevant host apps

| `--app=...`      | Source                                                          | Purpose                            |
|------------------|-----------------------------------------------------------------|------------------------------------|
| `CanApp`         | `app/app/SConscript:65`                                         | Full CAN COM stack on simulator    |
| `CanSimulator`   | `tools/libraries/Can/SConscript:70`                             | CAN broker (TCP/UDP)               |
| `CanDump`        | `tools/libraries/Can/SConscript:81`                             | Bus dump utility                   |
| `CanSend`        | `tools/libraries/Can/SConscript:93`                             | One-shot CAN sender                |
| `IsoTpSend`      | `tools/libraries/isotp/utils/isotp_send.c` (see build-env-setup)| ISO-TP / UDS tester                |
| `LinSimulator` / `LinSimulatorV2` | `tools/libraries/device/SConscript:25,38`      | LIN brokers                        |
| `CanIC`          | `app/app/SConscript:113`                                        | CanApp + VIC instrument cluster    |

Listing all registered apps/libs at the CLI is a side-effect of running
`scons` with no `--app`/`--lib` (`tools/building.py:2580-2590`).

---

## 4. Python interface — AsPy

### 4.1 Build

`AsPy` is a pybind11 extension built via SCons (`tools/building.py:1441`
adds the pybind11 include path). The asone bootstrap auto-builds it on
first import:

```python
# vendor/as/tools/asone/one/__init__.py:8-16
AsPy = "%s/build/%s/GCC/AsPy" % (ASROOT, os.name)
if not os.path.exists("%s/AsPy.%s" % (CWD, "pyd" if os.name=="nt" else "so")):
    # Windows:
    cmd = "cd %s & scons --lib=AsPy" % (ASROOT)
    cmd += "& cp -v %s/AsPy.dll %s/AsPy.pyd" % (AsPy, CWD)
    # Linux:
    cmd = "cd %s & scons --lib=AsPy" % (ASROOT)
    cmd += " && cp -v %s/AsPy.so %s/AsPy.so" % (AsPy, CWD)
    os.system(cmd)
```

Manual build:

```sh
cd vendor/as
scons --lib=AsPy
# Linux: build/posix/GCC/AsPy/AsPy.so
# Windows: copy build\nt\GCC\AsPy\AsPy.dll → AsPy.pyd next to your script
```

### 4.2 Surface area (used in-tree)

Confirmed submodules and call sites:

| Submodule         | Used by                                                           |
|-------------------|-------------------------------------------------------------------|
| `AsPy.can`        | `tools/asone/UIs/UICan.py:8`, `UISerial.py:12`, `utils/trace.py:121` |
| `AsPy.lin`        | `tools/asone/one/assignal.py:11`                                  |
| `AsPy.isotp`      | `tools/asone/one/dcm.py:10`                                       |
| `AsPy.bitarray`   | `tools/asone/UIs/UIDcm.py:9`                                      |
| `AsPy.lua`        | `tools/asone/UIs/UIDcm.py:10`                                     |
| `AsPy.loader`     | `tools/asone/UIs/UIFBL.py:9`                                      |

Verified Python API (from `docs/CN/virtual-can-env.md:80-122`):

```python
import AsPy
n0 = AsPy.can("simulator", 0)        # connect to TCP broker bus 0
n0.write(0x731, bytes(range(8)))     # True/False
ok, canid, data = n0.read(0x731)     # filter by ID; returns [bool,id,bytes]
```

`canlib.h` (referenced from the doc) exposes
`can_open`, `can_write`, `can_read`, `can_close`. The `AsPy.can` Python
wrapper mirrors these.

---

## 5. `asone` GUI tool

### 5.1 Python edition (always available)

Entry point: `vendor/as/tools/asone/main.py`. Run with:

```sh
cd vendor/as/tools/asone
python main.py
```

It auto-discovers `UIs/UI*.py` panels
(`tools/asone/main.py:35-43`). Shipped panels:

| Panel       | File                                | Purpose                               |
|-------------|-------------------------------------|---------------------------------------|
| `UICan`     | `tools/asone/UIs/UICan.py`          | Raw CAN send/receive                  |
| `UICom`     | `tools/asone/UIs/UICom.py`          | Signal-level COM with lua callbacks   |
| `UISerial`  | `tools/asone/UIs/UISerial.py`       | Serial monitor                        |
| `UIDcm`     | `tools/asone/UIs/UIDcm.py`          | UDS / Dcm tester (lua hooks)          |
| `UIFBL`     | `tools/asone/UIs/UIFBL.py`          | Flash bootloader client               |

UIDcm and UICom embed `AsPy.lua` and call user lua scripts on rx/tx —
see §5.3.

### 5.2 C++ / Qt edition

A higher-performance C++ port lives under `tools/asone/src/ui/`
(`UICom.cpp`, `UIDcm.cpp`, `UICan.cpp`, `UITester.cpp`, `UIXcp.hpp`,
`UITrace.hpp`, `UIVIC.hpp`, `figure/`). It is built as the `AsOne`
library:

```sh
scons --lib=AsOne
```

The README (`vendor/as/README.md:29`) recommends the C++ edition as "the
best"; same lua surface as the Python edition.

### 5.3 Lua engine (UICom / UIDcm)

Lua script shape, copied verbatim from `vendor/as/doc/EN/UICom.md:5-77`:

**Per-message script** (e.g. `RxMsgAbsInfo.lua`):

```lua
require("com")

period = 100
function init(signals)        -- called once; returns defaults + period
    return signals, period
end
function main(signals)        -- called every `period` ms
    signals.VehicleSpeed = ...
    year = com.get("CAN0.TxMsgTime.year")
    com.set("CAN0.TxMsgTime.year", year + 1)
    return signals, period
end
function on_rx(signals) ... end     -- Rx-message only
function on_tx() ... end            -- Tx-confirm only
```

**Global script** with figure plotting (`com.lua`):

```lua
require("com")
require("figure")
function init()
    figure.create({ name="figure0", titleX="x", titleY="y",
                    minX=0, maxX=100, minY=0, maxY=100,
                    lines={ {name="line0", type="line"} } })
    return 100
end
function main()
    figure.add_point("figure0", "line0", x, y)
    return 100
end
function on_rx_CAN0_TxMsgTime() ... end   -- naming: on_rx_<Net>_<Msg>
function on_tx_CAN0_RxMsgAbsInfo() ... end
```

Built-in lua modules: `com` (`com.get(path)`, `com.set(path, value)` where
`path = "<Net>.<Msg>.<Signal>"`), `figure` (graphing). The UIDcm panel
exposes additional dcm-side bindings via `AsPy.lua`.

Example lua scripts shipped: `tools/asone/examples/dcm.lua`,
`tools/asone/examples/xcp.lua`, `tools/asone/examples/Tester.lua`. Example
diag JSON: `tools/asone/examples/diagnostic.json`, `xcp.json`, `vic.json`.

---

## 6. Other utilities referenced from the repo

| Tool                                          | Path                                          |
|-----------------------------------------------|-----------------------------------------------|
| DBC parser used by Com/CanIf/PduR generators  | `tools/generator/dbc/`                        |
| LDF parser used by LinIf generator            | `tools/generator/ldf/`                        |
| OIL (OSEK) parser                             | `tools/generator/oil/`                        |
| Code-gen templates (jinja-ish)                | `tools/generator/templates/`                  |
| Utility CAN dump / send / trace               | `tools/libraries/Can/utils/`, `tools/utils/trace.py` |
| Loader / DoIPClient / IsoTp libraries         | `tools/libraries/loader, doipc, isotp`        |
| JSON-Editor DBC import plugin                 | `tools/json.editor/plugin/ImportDBC.py`       |

---

## 7. Things upstream does NOT provide (do not assume they exist)

- No formal JSON Schema (Draft-07 etc.) — only the GUI's annotated schema.
- No `class: "Can"` generator — `Can_Cfg.c` is hand-edited / pulled from
  `app/platform/<target>/src/config/`.
- No CLI subcommand on `python main.py` for "generate without GUI" — the GUI
  must be opened (or call `generator.Generate` directly per §2.2).
- No published REST or RPC interface around the generators.
- No machine-readable manifest of which JSON keys produce which `#define`s
  beyond reading the generator Python.

Anything OpenVinci wants on top of these (schema export, headless CLI,
batch validation API) is **new work that lives in OpenVinci**, not in
`vendor/as`. See `docs/ARCHITECTURE.md`.
