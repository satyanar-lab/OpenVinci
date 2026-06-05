# model/ — Layer-1 JSON Schemas

Draft 2020-12 schemas, one per `class` value the upstream generator
factory recognises (`vendor/as/tools/generator/__init__.py:44-76`):

| File                  | `class` discriminator | Upstream generator path                |
|-----------------------|-----------------------|----------------------------------------|
| `com.schema.json`     | `"Com"`               | `vendor/as/tools/generator/Com.py`     |
| `canif.schema.json`   | `"CanIf"`             | `vendor/as/tools/generator/CanIf.py`   |
| `cantp.schema.json`   | `"CanTp"`             | `vendor/as/tools/generator/CanTp.py`   |
| `pdur.schema.json`    | `"PduR"`              | `vendor/as/tools/generator/PduR.py`    |
| `can.schema.json`     | `"Can"`               | *(none — OpenVinci-only metadata around the hand-written `Can_Cfg.c`; see `docs/AUTOAS_NOTES.md` §1.2 "Can")* |
| `shared/types.schema.json` | —                | Shared `$defs` (`HexString`, `Identifier`, `BSWModule`, `NetworkKind`, `SimDevice`) |

Every schema sets `additionalProperties: true`. Upstream tolerates and
relies on extras — for example the `-name` / `-up` "soft-comment"
aliases in `vendor/as/app/app/config/Com/CanIf.json` and the
`backup-routines-secoc-test-over-cantp` and `backup-channels` keys.
Strict validation would reject those.

Each schema carries `vendoredAsCommit` naming the `vendor/as` SHA the
field tables were derived from. When the submodule moves, regenerate
the schemas against the new generator Python (`docs/ARCHITECTURE.md`
§"Layer 1").

## What's *not* here (and why)

Cross-file rules — e.g. "CanTp channel `X` requires CanIf `X_RX` /
`X_TX`" — cannot be expressed in JSON Schema. They live in Layer 2
(`backend/app/model/` Pydantic loaders today, Layer-2 engine when it
lands). See `docs/ARCHITECTURE.md` §2.2.
