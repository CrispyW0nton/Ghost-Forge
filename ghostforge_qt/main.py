from __future__ import annotations

import os
import sys
from pathlib import Path

from .app import run


def main(argv: list[str] | None = None) -> int:
    """Launch the Ghost Forge Qt editor."""

    # Lets tests and headless agents construct widgets without a display server.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    return run(argv if argv is not None else sys.argv[1:], app_dir=Path.cwd())


if __name__ == "__main__":
    raise SystemExit(main())
