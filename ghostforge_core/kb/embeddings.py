"""Embedders for the knowledge base.

`Embedder` is a small protocol so the KB can swap implementations without
leaking ML library imports into the rest of the core. Two concrete classes
ship today:

* :class:`HashEmbedder` — deterministic 256-dim embedder built only from the
  Python standard library plus Pillow. Always available; quality is "good
  enough" for unit tests and small style-guide corpora, intentionally not
  competitive with CLIP for image similarity.
* :class:`OpenCLIPEmbedder` — wraps ``open_clip_torch`` for true joint
  text/image embeddings. Loaded only when explicitly requested through
  :func:`make_embedder` to keep core boot times fast.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

# 256 keeps HashEmbedder vectors small and is plenty for hash-of-tokens style
# similarity. OpenCLIP variants typically use 512/768; we record the dim per
# embedder, never assume.
_HASH_DIM = 256


@runtime_checkable
class Embedder(Protocol):
    """Common surface for any embedder used by the KB."""

    name: str
    dim: int

    def embed_text(self, text: str) -> list[float]: ...
    def embed_image_bytes(self, data: bytes) -> list[float]: ...
    def embed_image_path(self, path: Path | str) -> list[float]: ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class HashEmbedder:
    """Deterministic text + image embedder with no ML dependencies.

    * Text is tokenised on whitespace; each token is hashed with SHA-256 and
      sprayed into the 256-dim vector via the *signed hashing trick* (used
      by scikit-learn's ``HashingVectorizer``). This produces stable, sparse
      vectors that capture lexical overlap.
    * Images are downsized to 16x16 grayscale, centered, and L2-normalised —
      effectively a perceptual hash. Similar-looking images (same crop, same
      colour distribution) score high; semantically similar images of
      different scenes do not. This is fine for tests and for the
      "is this the same source asset?" deduplication path.

    Cross-modal search (text query against image entries, or vice versa) is
    intentionally weak because text and image vectors live in different
    statistical spaces. Use OpenCLIP when cross-modal retrieval matters.
    """

    name = "hash:256"
    dim = _HASH_DIM

    def embed_text(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        if not text:
            return vec
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for offset in range(0, len(digest), 4):
                slot = int.from_bytes(digest[offset : offset + 4], "big") % self.dim
                sign = 1.0 if (digest[offset] & 1) else -1.0
                vec[slot] += sign
        return _l2_normalize(vec)

    def embed_image_bytes(self, data: bytes) -> list[float]:
        if not data:
            return [0.0] * self.dim
        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - Pillow is a hard dep
            raise RuntimeError("Pillow is required for image embeddings") from exc

        img = Image.open(io.BytesIO(data)).convert("L").resize((16, 16))
        # Pillow >= 11 deprecates `Image.getdata()` in favour of
        # `get_flattened_data()`; fall back to the old API for older releases
        # so we work across the whole supported range without warnings.
        flatten = getattr(img, "get_flattened_data", None)
        pixels = list(flatten()) if callable(flatten) else list(img.getdata())
        if not pixels:
            return [0.0] * self.dim
        mean = sum(pixels) / len(pixels)
        centered = [(p - mean) / 255.0 for p in pixels]
        # Pad / truncate to dim. 16x16 == 256 == dim today; this stays correct
        # if dim ever changes.
        if len(centered) < self.dim:
            centered.extend([0.0] * (self.dim - len(centered)))
        else:
            centered = centered[: self.dim]

        # Solid-colour images produce a zero-variance vector and would
        # otherwise hash to all zeros (and a 0 cosine similarity to anything).
        # Fall back to a deterministic mean-colour hash so solid red and solid
        # blue still have distinct, reproducible fingerprints.
        if not any(centered):
            digest = hashlib.sha256(
                f"solid:{int(round(mean))}".encode("ascii")
            ).digest()
            centered = [
                (digest[i % len(digest)] - 128) / 128.0 for i in range(self.dim)
            ]
        return _l2_normalize(centered)

    def embed_image_path(self, path: Path | str) -> list[float]:
        return self.embed_image_bytes(Path(path).read_bytes())


class OpenCLIPEmbedder:  # pragma: no cover - optional, exercised manually
    """Embedder backed by ``open_clip_torch``.

    Loaded lazily so importing this module never costs torch's startup time.
    Pass an explicit ``model_name`` (e.g. ``"ViT-B-32"``) and ``pretrained``
    (e.g. ``"laion2b_s34b_b79k"``) for deterministic behaviour across
    machines. Defaults follow the OpenCLIP recommended baseline.
    """

    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
        device: str | None = None,
    ) -> None:
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "OpenCLIP embedder requested but `open_clip_torch` / `torch` "
                "are not installed. Install the `kb` extras."
            ) from exc

        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=self.device
        )
        self._model.eval()
        self._tokenizer = open_clip.get_tokenizer(model_name)
        self.name = f"openclip:{model_name}:{pretrained}"
        with torch.no_grad():
            dummy = self._tokenizer(["probe"]).to(self.device)
            features = self._model.encode_text(dummy)
            self.dim = int(features.shape[-1])

    def embed_text(self, text: str) -> list[float]:
        torch = self._torch
        with torch.no_grad():
            tokens = self._tokenizer([text or ""]).to(self.device)
            features = self._model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
            return features[0].cpu().tolist()

    def embed_image_bytes(self, data: bytes) -> list[float]:
        from PIL import Image

        return self._embed_pil(Image.open(io.BytesIO(data)).convert("RGB"))

    def embed_image_path(self, path: Path | str) -> list[float]:
        from PIL import Image

        return self._embed_pil(Image.open(Path(path)).convert("RGB"))

    def _embed_pil(self, image) -> list[float]:
        torch = self._torch
        with torch.no_grad():
            tensor = self._preprocess(image).unsqueeze(0).to(self.device)
            features = self._model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
            return features[0].cpu().tolist()


def make_embedder(name: str | None = None) -> Embedder:
    """Resolve an embedder from a short name.

    Resolution order:

    1. Explicit ``name`` argument.
    2. ``GHOSTFORGE_KB_EMBEDDER`` environment variable.
    3. Default: :class:`HashEmbedder` (always available).

    Recognised values are ``hash`` and ``openclip``.
    """
    resolved = (name or os.environ.get("GHOSTFORGE_KB_EMBEDDER") or "hash").lower()
    if resolved in {"hash", "hashing", "hash:256"}:
        return HashEmbedder()
    if resolved.startswith("openclip"):
        # Allow "openclip", "openclip:ViT-B-32", or "openclip:ViT-B-32:openai".
        parts = resolved.split(":")
        kwargs: dict[str, str] = {}
        if len(parts) >= 2 and parts[1]:
            kwargs["model_name"] = parts[1]
        if len(parts) >= 3 and parts[2]:
            kwargs["pretrained"] = parts[2]
        return OpenCLIPEmbedder(**kwargs)
    raise ValueError(f"Unknown embedder: {name!r}")


__all__ = [
    "Embedder",
    "HashEmbedder",
    "OpenCLIPEmbedder",
    "make_embedder",
]
