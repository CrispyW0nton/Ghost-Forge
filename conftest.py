"""Top-level pytest configuration.

Provides:

* A ``gpu`` marker for tests that need a real CUDA device. Without
  ``--run-gpu`` they are skipped automatically — that lets the bulk of
  the suite stay green on CPU-only CI runners while keeping the heavy
  paths exercised on hosts that opt in.

* A ``heavy_deps`` marker for tests that need optional ML packages
  (``torch``, ``diffusers``, ``open_clip_torch``). They are auto-skipped
  when the imports are missing.
"""

from __future__ import annotations

import importlib
from typing import Iterable

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-gpu",
        action="store_true",
        default=False,
        help=(
            "Run tests marked with @pytest.mark.gpu (require a real "
            "CUDA-capable GPU and the `ai` extras installed)."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "gpu: tests that require a CUDA GPU (run with --run-gpu).",
    )
    config.addinivalue_line(
        "markers",
        "heavy_deps(modules): tests requiring optional ML packages.",
    )


def _missing(modules: Iterable[str]) -> list[str]:
    out = []
    for name in modules:
        try:
            importlib.import_module(name)
        except ImportError:
            out.append(name)
    return out


def pytest_collection_modifyitems(  # type: ignore[no-untyped-def]
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_gpu = bool(config.getoption("--run-gpu"))

    for item in items:
        gpu_mark = item.get_closest_marker("gpu")
        if gpu_mark is not None and not run_gpu:
            item.add_marker(
                pytest.mark.skip(reason="gpu test (rerun with --run-gpu)")
            )

        heavy_mark = item.get_closest_marker("heavy_deps")
        if heavy_mark is not None:
            modules = heavy_mark.args or ()
            missing = _missing(modules)
            if missing:
                item.add_marker(
                    pytest.mark.skip(
                        reason=f"missing optional modules: {missing}"
                    )
                )
