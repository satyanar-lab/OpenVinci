# model/ — shared JSON Schemas

This directory will hold the Layer-1 schemas described in
`docs/ARCHITECTURE.md` §"Layer 1 — Model". Each schema corresponds to
a `class` key recognized by `vendor/as`'s generator factory
(`vendor/as/tools/generator/__init__.py:44-76`):

```
model/
  com.schema.json        # planned
  canif.schema.json      # planned
  cantp.schema.json      # planned
  pdur.schema.json       # planned
  shared/                # shared $defs (PduRef, NetworkRef, hex int, …)
```

Schemas will be authored from the generator Python, the GUI schema at
`vendor/as/tools/json.editor/schema.json`, and the doc-comments under
`vendor/as/doc/EN/`. See `docs/AUTOAS_NOTES.md` §1.2 for the per-module
field tables they need to cover.

The frontend fetches these from the backend's `/schemas` endpoint at
runtime — they are not bundled into the JS.
