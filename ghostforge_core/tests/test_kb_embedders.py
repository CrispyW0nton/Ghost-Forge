from __future__ import annotations

import io
import math

import pytest

from ghostforge_core.kb.embeddings import HashEmbedder, make_embedder


def _norm(vec):
    return math.sqrt(sum(x * x for x in vec))


def test_hash_embedder_metadata():
    e = HashEmbedder()
    assert e.name == "hash:256"
    assert e.dim == 256


def test_hash_embedder_text_deterministic_and_normalised():
    e = HashEmbedder()
    a = e.embed_text("ancient greek temple")
    b = e.embed_text("ancient greek temple")
    assert a == b
    assert pytest.approx(_norm(a), rel=1e-6) == 1.0
    assert len(a) == e.dim


def test_hash_embedder_text_distinguishes_overlap():
    e = HashEmbedder()
    a = e.embed_text("ancient greek temple")
    b = e.embed_text("ancient greek temple stone marble")
    c = e.embed_text("steampunk airship cockpit chrome")
    sim_ab = sum(x * y for x, y in zip(a, b))
    sim_ac = sum(x * y for x, y in zip(a, c))
    assert sim_ab > sim_ac


def test_hash_embedder_image_bytes_round_trip():
    pil = pytest.importorskip("PIL.Image")
    pil_draw = pytest.importorskip("PIL.ImageDraw")

    img = pil.new("RGB", (32, 32), color=(127, 64, 200))
    draw = pil_draw.Draw(img)
    # Add structure so the embedding has non-zero variance and round-trips
    # through the cosine search realistically.
    draw.rectangle((4, 4, 14, 14), fill=(20, 220, 50))
    draw.line((0, 0, 31, 31), fill=(0, 0, 0), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    e = HashEmbedder()
    a = e.embed_image_bytes(data)
    b = e.embed_image_bytes(data)
    assert a == b
    assert len(a) == e.dim
    assert _norm(a) == pytest.approx(1.0, abs=1e-6)


def test_hash_embedder_solid_color_fallback_is_non_zero():
    pil = pytest.importorskip("PIL.Image")
    e = HashEmbedder()

    def _bytes(rgb):
        img = pil.new("RGB", (32, 32), color=rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    red = e.embed_image_bytes(_bytes((220, 30, 30)))
    blue = e.embed_image_bytes(_bytes((30, 30, 220)))
    assert _norm(red) == pytest.approx(1.0, abs=1e-6)
    assert _norm(blue) == pytest.approx(1.0, abs=1e-6)
    # Different solid colours must produce different deterministic vectors.
    assert red != blue


def test_make_embedder_default_is_hash():
    e = make_embedder()
    assert isinstance(e, HashEmbedder)


def test_make_embedder_rejects_unknown_name():
    with pytest.raises(ValueError):
        make_embedder("magic-bag-of-features")
