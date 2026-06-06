# examples/dbc — DBC fixtures

Real-world DBC files used to exercise the OpenVinci importer +
auto-wire + generate + compile chain. Every file in this directory
parses cleanly with `cantools` (which the importer uses) and the
resulting project compiles clean at VERIFICATION LEVEL 1 — see
`backend/tests/test_dbc_matrix.py`.

| File | Source | Origin / notes |
|------|--------|----------------|
| `sample.dbc` | OpenVinci (hand-written) | Two messages, one Tx + one Rx, with scaled and signed signals — the smoke fixture used in `docs/DEMO.md`. |
| `motohawk.dbc` | [cantools](https://github.com/cantools/cantools) tests | Classic engine-ECU test fixture. One message (`ExampleMessage`), three signals (`Enable`, `AverageRadius`, `Temperature`). Big-endian. |
| `motohawk_fd.dbc` | cantools tests | CAN-FD variant of `motohawk.dbc`. Same shape (dlc=8); exercises the `is_fd → message.fd` importer path at a Classic-compatible length. |
| `fd-payload.dbc` | OpenVinci (hand-written) | Two FD messages (`FD_TX`, `FD_RX`) with dlc=16. Exercises the FD-dlc>8 path in the importer + the `com.message-dlc-valid` engine rule. |
| `foobar.dbc` | cantools tests | Five messages, four senders (`FOO`, `BAR`, `FIE`, `FUM`). Mixed direction; good multi-node integration check. |
| `j1939.dbc` | cantools tests | Two messages using the J1939 protocol. Exercises larger frame IDs. |
| `multiple_senders.dbc` | cantools tests | A single message declared with multiple senders — edge case for the importer's "first sender wins" choice. |
| `socialledge.dbc` | cantools tests | Five messages, multiplexed signals. Multiplexing is not yet modelled by OpenVinci — the signals collapse to flat signals, the compile is still clean. |
| `vehicle.dbc` | cantools tests | 217 messages / 462 signals — the largest scale stress test in the matrix. |
| `subaru_forester_2017.dbc` | [opendbc](https://github.com/commaai/opendbc) | Subset of a real Subaru DBC. Two messages (`ES_DashStatus`, etc.). |
| `honda_civic_touring_2016.dbc` | opendbc | Two real Honda Civic messages. |
| `toyota_tnga_k_pt.dbc` | opendbc | Two real Toyota powertrain messages. |

## Licensing

Both source repos are **MIT-licensed**:

- cantools — https://github.com/cantools/cantools/blob/master/LICENSE
- opendbc — https://github.com/commaai/opendbc/blob/master/LICENSE

OpenVinci copies a small selection verbatim and inherits the MIT terms
for those files. The originals are unmodified — the files here are
byte-identical to the source repos at the commits they were copied
from. If you need an SBOM-grade record of the copy provenance, the
file mtimes in this directory match the clone time of the source
repos, and the originals are still online at the URLs above.

## Try one

```sh
# Import any of these into a fresh project + auto-wire + validate:
backend/.venv/bin/openvinci-import-dbc examples/dbc/motohawk.dbc \
    --out /tmp/motohawk-demo --network CAN0 --me PCM1 --force

# Or drop it into the UI:
make dev   # → http://localhost:5173 → Import DBC → drop file
```

## What's tested

`backend/tests/test_dbc_matrix.py` parametrizes over every file in
this directory and asserts, for each one:

1. `parse_dbc(path)` returns a non-empty list of messages.
2. `import_dbc_file(path, …)` produces a Project with every modeled
   module (`Can`, `Com`, `CanIf`, `PduR`).
3. The engine's `validate()` reports `ok=True`.
4. The gen pipeline produces a clean L1 compile against the BSW
   headers.

That's 11 DBCs × 4 levels of assertion per file = the broad
coverage layer for the importer.
