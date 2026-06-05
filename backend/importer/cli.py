"""CLI entry point — `openvinci-import-dbc`.

    openvinci-import-dbc DBC --out PROJECT_DIR [--network CAN0] [--me AS]

Parses the DBC, builds + auto-wires a Project, and writes the four
modeled module JSONs (Com, CanIf, PduR, Can) into PROJECT_DIR using
the layout vendor/as expects (`config/<Module>/<Module>.json`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.project import CLASS_TO_PATH

from . import import_dbc_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="openvinci-import-dbc",
        description="Import a CAN .dbc into a fresh OpenVinci project + auto-wire.",
    )
    parser.add_argument("dbc", help="path to a .dbc file")
    parser.add_argument("--out", required=True, help="output project directory")
    parser.add_argument("--network", default="CAN0", help="network name (default: CAN0)")
    parser.add_argument("--me", default="AS", help="self node name (default: AS)")
    parser.add_argument(
        "--baudrate", type=int, default=500000, help="CAN baud rate (default: 500000)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing JSONs in --out",
    )
    args = parser.parse_args(argv)

    dbc_path = Path(args.dbc)
    out_dir = Path(args.out)
    if not dbc_path.is_file():
        print(f"error: {dbc_path}: file not found", file=sys.stderr)
        return 2

    project = import_dbc_file(
        dbc_path,
        network_name=args.network,
        me=args.me,
        baudrate=args.baudrate,
    )

    written: list[Path] = []
    for cls in ("Can", "Com", "CanIf", "PduR"):
        raw = project.raw.get(cls)
        if raw is None:
            continue
        path = out_dir / CLASS_TO_PATH[cls]
        if path.exists() and not args.force:
            print(f"error: {path} exists (pass --force to overwrite)", file=sys.stderr)
            return 3
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2) + "\n")
        written.append(path)

    print(f"wrote {len(written)} files to {out_dir}:")
    for p in written:
        print(f"  {p.relative_to(out_dir)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
