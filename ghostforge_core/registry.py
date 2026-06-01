from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import Field

from .types import FrozenModel


class HandlerDescriptor(FrozenModel):
    kind: str
    capabilities: list[str] = Field(default_factory=list)
    version: str = "0.1.0"


class Registry:
    def __init__(self) -> None:
        self._handlers: dict[str, tuple[HandlerDescriptor, Callable[..., Any]]] = {}

    def register(
        self,
        kind: str,
        handler: Callable[..., Any],
        *,
        capabilities: list[str] | None = None,
        version: str = "0.1.0",
    ) -> HandlerDescriptor:
        descriptor = HandlerDescriptor(
            kind=kind,
            capabilities=capabilities or [],
            version=version,
        )
        self._handlers[kind] = (descriptor, handler)
        return descriptor

    def get(self, kind: str) -> Callable[..., Any]:
        return self._handlers[kind][1]

    def describe(self, kind: str) -> HandlerDescriptor:
        return self._handlers[kind][0]

    def list(self) -> list[HandlerDescriptor]:
        return [descriptor for descriptor, _ in self._handlers.values()]

    def has(self, kind: str) -> bool:
        return kind in self._handlers
