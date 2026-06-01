"""Qt desktop shell for Ghost Forge.

This package is the start of the PySide6 migration. It deliberately wraps the
existing :mod:`ghostforge_core` instead of replacing it, so the desktop editor,
HTTP bridge, and MCP server can keep sharing one asset pipeline.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
