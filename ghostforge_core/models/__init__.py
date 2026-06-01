"""Model artifact registry.

Workers declare which models they need by id (see
:attr:`Worker.required_models`). The :class:`ModelRegistry` is the
single source of truth for what each id resolves to: an HF Hub repo,
the file paths inside it, and a sha256-verified cache under
``data/cache/models/``.

Public surface:

* :class:`ModelArtifact`, :class:`ModelFile`, :class:`ModelStatus` —
  Pydantic schemas, safe to send across MCP.
* :class:`ModelRegistry` — register/list/download/verify/clear.
* :data:`DEFAULT_ARTIFACTS` — pinned defaults that ship with
  GhostForge; ``bootstrap`` registers them automatically.
"""

from __future__ import annotations

from .defaults import DEFAULT_ARTIFACTS
from .registry import ModelDownloadError, ModelNotFound, ModelRegistry
from .schema import ModelArtifact, ModelFile, ModelStatus

__all__ = [
    "DEFAULT_ARTIFACTS",
    "ModelArtifact",
    "ModelDownloadError",
    "ModelFile",
    "ModelNotFound",
    "ModelRegistry",
    "ModelStatus",
]
