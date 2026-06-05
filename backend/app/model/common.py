"""Base class shared by every OpenVinci config model.

The `extra="allow"` choice is load-bearing. Real upstream configs carry
keys we deliberately do not type — `-name` / `-up` "soft-comment"
aliases in `app/app/config/Com/CanIf.json`, `backup-channels` in
`app/app/config/CanTp/CanTp.json`, etc. Strict validation would reject
those and break round-trip. See docs/AUTOAS_NOTES.md §1 for the worked
examples.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class OpenVinciModel(BaseModel):
    """All module models inherit from this so dump options are uniform."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )

    def to_jsonable(self) -> dict[str, Any]:
        """Round-trip-safe dump: only the fields the user supplied come back.

        - `by_alias=True` so Python-keyword fields (`class`, `from`) emit
          their upstream JSON key.
        - `exclude_unset=True` so optional fields that weren't in the
          source don't materialise as `null`s in the output.
        - `mode="json"` so the result is plain JSON-types only.
        """
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")
