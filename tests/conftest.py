"""Root pytest plugin: shared CLI options for tests/ subdirs."""

from __future__ import annotations


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help=(
            "Overwrite golden snapshots under tests/golden/<example>/expected/ "
            "instead of asserting equality. Use after intentional changes to "
            "the generated output, then commit the new snapshots."
        ),
    )
