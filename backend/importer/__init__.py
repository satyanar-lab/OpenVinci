"""OpenVinci importer layer — communication-matrix import + auto-wire.

Today: CAN .dbc files via `cantools`. Tomorrow: LDF for LIN, ARXML, etc.
Every importer follows the same shape:

    raw_file → list of Com messages → merge into Project.com → auto-wire
    PduR / CanIf / Can via the engine's derive functions.

That last step keeps the importer thin: the rules in `engine/rules.py`
already know how to add CanIf PDUs and PduR routines that match
vendor/as's macro convention.
"""

from .dbc import (
    auto_wire_from_com,
    import_dbc_file,
    parse_dbc,
)

__all__ = [
    "auto_wire_from_com",
    "import_dbc_file",
    "parse_dbc",
]
