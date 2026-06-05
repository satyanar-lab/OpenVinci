"""OpenVinci in-memory model layer.

Pydantic models that mirror the JSON Schemas under `/model/*.schema.json`,
plus a loader and serializer used by Layer 2. Designed for bit-perfect
round-trip of `vendor/as` configs: declared fields are typed; anything
upstream sends that we did not model survives via `extra="allow"`.

See docs/ARCHITECTURE.md §"Layer 1" / §"Layer 2".
"""

from .common import OpenVinciModel
from .loader import (
    SUPPORTED_CLASSES,
    UnknownConfigClassError,
    dump,
    dump_to_path,
    load,
    load_from_path,
)
from .can import CanConfig
from .canif import CanIfConfig
from .cantp import CanTpConfig
from .pdur import PduRConfig
from .com import ComConfig

__all__ = [
    "OpenVinciModel",
    "SUPPORTED_CLASSES",
    "UnknownConfigClassError",
    "dump",
    "dump_to_path",
    "load",
    "load_from_path",
    "CanConfig",
    "CanIfConfig",
    "CanTpConfig",
    "PduRConfig",
    "ComConfig",
]
