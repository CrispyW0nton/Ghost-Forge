"""Ingestion helpers for the knowledge base.

Three paths are supported today:

* ``ingest_local_image`` — paths the user already has on disk.
* ``ingest_url`` — a single image URL with hand-supplied license.
* ``ingest_openverse`` — a license-aware search against Openverse's public
  REST API.

Network calls use ``urllib`` from the standard library to keep the KB free
of third-party HTTP dependencies. A ``Fetcher`` callable is injected for
testability — pass ``fetcher=fake`` from tests to avoid network IO.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Protocol

from .base import KnowledgeBase
from .schema import ConceptEntry, ConceptSource

# Default API endpoint. Hidden behind an env variable so deployments can
# point at a self-hosted Openverse mirror or a recorded fixture.
import os

OPENVERSE_DEFAULT_BASE = os.environ.get(
    "GHOSTFORGE_OPENVERSE_BASE", "https://api.openverse.engineering/v1"
)
OPENVERSE_USER_AGENT = "GhostForge/0.1 (+https://github.com/CrispyW0nton/Ghost-Forge)"


class Fetcher(Protocol):
    def __call__(self, url: str, *, accept: str | None = ...) -> bytes: ...


def default_fetcher(url: str, *, accept: str | None = None) -> bytes:
    """Tiny urllib wrapper that adds a User-Agent and optional Accept header.

    Openverse rejects requests without a user agent; we set one explicitly
    so we play nice with their public API. Timeout is conservative because
    the desktop app should never block on a single concept image.
    """
    request = urllib.request.Request(url)
    request.add_header("User-Agent", OPENVERSE_USER_AGENT)
    if accept:
        request.add_header("Accept", accept)
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read()


def ingest_local_image(
    kb: KnowledgeBase,
    path: Path | str,
    *,
    title: str,
    license: str,
    description: str = "",
    attribution: str | None = None,
    creator: str | None = None,
    tags: list[str] | None = None,
    source_url: str | None = None,
) -> ConceptEntry:
    """Ingest a file already present on disk."""
    return kb.add_image_path(
        path,
        title=title,
        license=license,
        source=ConceptSource.local,
        description=description,
        attribution=attribution,
        creator=creator,
        tags=tags,
        source_url=source_url,
    )


def ingest_url(
    kb: KnowledgeBase,
    url: str,
    *,
    title: str,
    license: str,
    description: str = "",
    attribution: str | None = None,
    creator: str | None = None,
    tags: list[str] | None = None,
    license_url: str | None = None,
    fetcher: Fetcher | None = None,
) -> ConceptEntry:
    """Download an image and ingest it. License is mandatory."""
    fetch = fetcher or default_fetcher
    data = fetch(url, accept="image/*")
    return kb.add_image(
        image_bytes=data,
        title=title,
        license=license,
        source=ConceptSource.url,
        description=description,
        source_url=url,
        license_url=license_url,
        attribution=attribution,
        creator=creator,
        tags=tags,
    )


# Openverse tags every result with a ``license`` plus an SPDX-like identifier.
# We restrict ingestion to permissive licenses by default so users don't
# accidentally pull copyrighted material into their pipeline.
_OPENVERSE_PERMISSIVE = {"cc0", "pdm", "by", "by-sa"}


def ingest_openverse(
    kb: KnowledgeBase,
    query: str,
    *,
    license_filter: Iterable[str] | None = None,
    count: int = 5,
    page_size: int | None = None,
    api_base: str | None = None,
    fetcher: Fetcher | None = None,
    tag_prefix: str = "openverse",
) -> list[ConceptEntry]:
    """Search Openverse and ingest the top ``count`` results.

    ``license_filter`` defaults to permissive licenses (cc0, pdm, by, by-sa).
    Each ingested entry records the originating Openverse license, attribution
    string, and source URL so downstream citations stay accurate even if the
    upstream record disappears.
    """
    base = (api_base or OPENVERSE_DEFAULT_BASE).rstrip("/")
    fetch = fetcher or default_fetcher
    licenses = ",".join(sorted(license_filter or _OPENVERSE_PERMISSIVE))
    params = {
        "q": query,
        "license": licenses,
        "page_size": str(page_size or max(count, 5)),
    }
    search_url = f"{base}/images/?{urllib.parse.urlencode(params)}"
    payload = json.loads(fetch(search_url, accept="application/json"))

    results = payload.get("results", []) or []
    ingested: list[ConceptEntry] = []
    for record in results[:count]:
        image_url = record.get("url") or record.get("thumbnail")
        if not image_url:
            continue
        license_id = record.get("license") or "unknown"
        license_version = record.get("license_version") or ""
        license_label = (
            f"CC-{license_id.upper()}-{license_version}".rstrip("-")
            if license_id not in {"cc0", "pdm"}
            else license_id.upper()
        )
        try:
            data = fetch(image_url, accept="image/*")
        except Exception:
            # A single broken image must not abort the batch — record the
            # failure on stderr-level logging in the caller, not here.
            continue
        title = record.get("title") or query
        attribution = record.get("attribution") or _attribution_string(record)
        entry = kb.add_image(
            image_bytes=data,
            title=title,
            license=license_label,
            source=ConceptSource.openverse,
            description=record.get("description") or "",
            source_url=record.get("foreign_landing_url") or image_url,
            license_url=record.get("license_url"),
            attribution=attribution,
            creator=record.get("creator"),
            tags=[tag_prefix, *_extract_tag_names(record.get("tags"))],
            metadata={
                "openverse_id": record.get("id"),
                "openverse_provider": record.get("provider"),
                "openverse_source": record.get("source"),
            },
        )
        ingested.append(entry)
    return ingested


def _extract_tag_names(tags: list[dict] | None) -> list[str]:
    if not tags:
        return []
    names: list[str] = []
    for tag in tags:
        if isinstance(tag, dict):
            name = tag.get("name")
            if name:
                names.append(str(name))
        elif isinstance(tag, str):
            names.append(tag)
    return names


def _attribution_string(record: dict) -> str | None:
    creator = record.get("creator")
    title = record.get("title")
    license_id = record.get("license")
    license_version = record.get("license_version")
    if not creator and not title:
        return None
    parts = [f'"{title}"' if title else None, f"by {creator}" if creator else None]
    if license_id:
        license_token = license_id.upper()
        if license_version:
            license_token = f"{license_token} {license_version}"
        parts.append(f"licensed under CC {license_token}")
    return " ".join(p for p in parts if p)


__all__ = [
    "Fetcher",
    "default_fetcher",
    "ingest_local_image",
    "ingest_openverse",
    "ingest_url",
]
