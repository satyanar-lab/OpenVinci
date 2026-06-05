"""Loader + serializer dispatched by the top-level `"class"` discriminator.

The discriminator scheme matches `vendor/as/tools/generator/__init__.py:44`
(`__GEN__` dict). Unknown classes raise rather than silently passing through.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

from .can import CanConfig
from .canif import CanIfConfig
from .cantp import CanTpConfig
from .com import ComConfig
from .common import OpenVinciModel
from .pdur import PduRConfig

AnyConfig = Union[CanConfig, CanIfConfig, CanTpConfig, PduRConfig, ComConfig]

SUPPORTED_CLASSES: dict[str, type[OpenVinciModel]] = {
    "Can": CanConfig,
    "CanIf": CanIfConfig,
    "CanTp": CanTpConfig,
    "PduR": PduRConfig,
    "Com": ComConfig,
}


class UnknownConfigClassError(ValueError):
    pass


def _dispatch(data: dict[str, Any]) -> type[OpenVinciModel]:
    cls = data.get("class")
    if cls not in SUPPORTED_CLASSES:
        raise UnknownConfigClassError(
            f"unknown 'class' value {cls!r}; supported: {sorted(SUPPORTED_CLASSES)}"
        )
    return SUPPORTED_CLASSES[cls]


def load(data: dict[str, Any]) -> AnyConfig:
    """Parse an already-decoded JSON dict into the matching model."""
    model_cls = _dispatch(data)
    return model_cls.model_validate(data)


def load_from_path(path: str | Path) -> AnyConfig:
    """Read a JSON file and parse it into the matching model."""
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return load(raw)


def dump(model: OpenVinciModel) -> dict[str, Any]:
    """Serialize the model back to a JSON-ready dict."""
    return model.to_jsonable()


def dump_to_path(model: OpenVinciModel, path: str | Path, *, indent: int = 2) -> None:
    Path(path).write_text(json.dumps(dump(model), indent=indent) + "\n")
