# canapp-min — minimal COM-stack example

A direct copy of four configs from `vendor/as/app/app/config/`:

| File             | Source                                     |
|------------------|--------------------------------------------|
| `Com/Com.json`   | `vendor/as/app/app/config/Com/Com.json`    |
| `Com/CanIf.json` | `vendor/as/app/app/config/Com/CanIf.json`  |
| `Com/PduR.json`  | `vendor/as/app/app/config/Com/PduR.json`   |
| `CanTp/CanTp.json` | `vendor/as/app/app/config/CanTp/CanTp.json` |

`Com.json` references `"../E2E/E2E.json"` and `Com/CAN0.dbc`; neither file
is included here. The configs still parse as JSON (which is all the
stub `/api/config` endpoint needs); generating C from them requires the
full surrounding project tree under `vendor/as/`.
