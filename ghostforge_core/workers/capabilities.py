"""Capability tags shared by workers and dispatch handlers."""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    """Generation capabilities a worker can advertise.

    Capability tags are the canonical contract between agents and workers.
    Agents request a capability; the registry picks the highest-priority
    runnable worker that advertises it. Adding a new generation modality
    means adding a value here, a request schema, and a dispatch handler.
    """

    image_to_3d = "image_to_3d"
    text_to_3d = "text_to_3d"
    texture_mesh = "texture_mesh"
    refine_mesh = "refine_mesh"


__all__ = ["Capability"]
