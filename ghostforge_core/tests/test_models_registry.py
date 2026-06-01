"""Model registry: registration, status, download (direct URL), verify, clear."""

from __future__ import annotations

import hashlib
import http.server
import socketserver
import threading
from pathlib import Path

import pytest

from ghostforge_core.models import (
    DEFAULT_ARTIFACTS,
    ModelArtifact,
    ModelDownloadError,
    ModelFile,
    ModelNotFound,
    ModelRegistry,
)


def test_register_and_list(tmp_path: Path):
    registry = ModelRegistry(tmp_path)
    registry.register_many(DEFAULT_ARTIFACTS)
    ids = {a.model_id for a in registry.list()}
    assert "trellis-image-large" in ids
    assert "hunyuan3d-2" in ids


def test_status_reports_missing_files(tmp_path: Path):
    registry = ModelRegistry(tmp_path)
    registry.register_many(DEFAULT_ARTIFACTS)
    status = registry.status("triposg")
    assert status.cached is False
    assert status.files_present == 0
    assert status.missing_files == ["model.safetensors"]
    assert status.integrity == "unknown"


def test_get_unknown_model_raises(tmp_path: Path):
    registry = ModelRegistry(tmp_path)
    with pytest.raises(ModelNotFound):
        registry.get("does-not-exist")


def test_clear_removes_cache_dir(tmp_path: Path):
    registry = ModelRegistry(tmp_path)
    registry.register(
        ModelArtifact(
            model_id="dummy",
            repo_id="https://example.invalid/dummy",
            files=[ModelFile(path="weights.bin", sha256="")],
        )
    )
    cache = registry.model_dir("dummy")
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "weights.bin").write_bytes(b"hi")
    assert cache.exists() and (cache / "weights.bin").exists()
    removed = registry.clear("dummy")
    assert removed == 1
    assert not cache.exists()


def test_model_id_is_path_safe(tmp_path: Path):
    registry = ModelRegistry(tmp_path)
    # Even with a hostile id, the cache dir stays inside cache_root.
    target = registry.model_dir("../../escape")
    assert target.parent == registry.cache_root
    assert target.name == "escape"


def test_direct_url_download_and_verify(tmp_path: Path):
    """End-to-end download via local HTTP server, sha256 verified."""

    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    payload = b"GhostForge model bytes\n"
    (serve_dir / "weights.bin").write_bytes(payload)
    expected_sha = hashlib.sha256(payload).hexdigest()

    handler = http.server.SimpleHTTPRequestHandler

    class _Handler(handler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(serve_dir), **kwargs)

        def log_message(self, format, *args):  # noqa: A003 - silence test logs
            return

    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        registry = ModelRegistry(tmp_path / "cache")
        registry.register(
            ModelArtifact(
                model_id="dummy-direct",
                repo_id=f"http://127.0.0.1:{port}",
                files=[ModelFile(path="weights.bin", sha256=expected_sha)],
            )
        )
        status = registry.download("dummy-direct")
        assert status.cached is True
        assert status.integrity == "verified"
        cached = registry.model_dir("dummy-direct") / "weights.bin"
        assert cached.read_bytes() == payload
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_direct_url_download_sha_mismatch_raises(tmp_path: Path):
    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    (serve_dir / "weights.bin").write_bytes(b"ABC")

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(serve_dir), **kwargs)

        def log_message(self, format, *args):  # noqa: A003
            return

    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        registry = ModelRegistry(tmp_path / "cache")
        registry.register(
            ModelArtifact(
                model_id="dummy-bad",
                repo_id=f"http://127.0.0.1:{port}",
                files=[ModelFile(path="weights.bin", sha256="0" * 64)],
            )
        )
        with pytest.raises(ModelDownloadError):
            registry.download("dummy-bad")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_idempotent_download_after_verified(tmp_path: Path):
    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    payload = b"x" * 17
    (serve_dir / "weights.bin").write_bytes(payload)
    expected_sha = hashlib.sha256(payload).hexdigest()

    fetch_count = {"n": 0}

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(serve_dir), **kwargs)

        def log_message(self, format, *args):  # noqa: A003
            return

        def do_GET(self):  # noqa: N802 - http.server callback
            fetch_count["n"] += 1
            super().do_GET()

    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        registry = ModelRegistry(tmp_path / "cache")
        registry.register(
            ModelArtifact(
                model_id="dummy-idem",
                repo_id=f"http://127.0.0.1:{port}",
                files=[ModelFile(path="weights.bin", sha256=expected_sha)],
            )
        )
        registry.download("dummy-idem")
        registry.download("dummy-idem")
        registry.download("dummy-idem")
        assert fetch_count["n"] == 1, "verified cache should not re-fetch"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
