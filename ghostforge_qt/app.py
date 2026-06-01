from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ghostforge_core import CoreConfig

from .services.core_bridge import CoreBridge
from .windows.main_window import MainWindow

log = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Ghost Forge Qt.")
    parser.add_argument(
        "--data-root",
        default=None,
        help="Override Ghost Forge data root. Defaults to ./data.",
    )
    parser.add_argument(
        "--no-dispatch",
        action="store_true",
        help="Record jobs without dispatching them in this process.",
    )
    return parser.parse_args(argv)


def create_app(argv: list[str] | None = None) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(argv or [])
    app.setApplicationName("Ghost Forge")
    app.setOrganizationName("Ghost Forge")
    app.setApplicationVersion("0.1.0")
    return app


def build_main_window(
    *,
    data_root: Path | None = None,
    dispatch_jobs: bool = True,
) -> MainWindow:
    config = CoreConfig(
        data_root=data_root or Path("./data"),
        dispatch_jobs=dispatch_jobs,
    )
    bridge = CoreBridge(config=config)
    return MainWindow(bridge=bridge)


def run(argv: list[str] | None = None, *, app_dir: Path | None = None) -> int:
    args = _parse_args(argv or [])
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    app = create_app(sys.argv[:1])
    data_root = Path(args.data_root) if args.data_root else None
    window = build_main_window(
        data_root=data_root,
        dispatch_jobs=not args.no_dispatch,
    )
    window.resize(1440, 900)
    window.show()
    return app.exec()
