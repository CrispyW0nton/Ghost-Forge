from __future__ import annotations

import json
from pathlib import Path

import pytest

from ghostforge_core.workers import Capability, WorkerUnavailable
from ghostforge_core.workers.schemas import TextTo3DRequest
from ghostforge_core.workers.tripo_api import (
    DEFAULT_MODEL_VERSION,
    TripoAPIWorker,
)


class _FakeTripoClient:
    api_base = "https://api.tripo3d.ai/v2/openapi"

    def __init__(self) -> None:
        self.payload: dict | None = None
        self.downloaded_url: str | None = None

    def submit_text_to_model(self, payload: dict):
        self.payload = dict(payload)
        return {"task_id": "task-123"}

    def wait_for_task(self, task_id: str, *, reporter=None, cancel=None):
        assert task_id == "task-123"
        return {
            "task_id": task_id,
            "status": "success",
            "output": {
                "pbr_model": "https://example.invalid/task-123.glb",
                "rendered_image": "https://example.invalid/task-123.png",
            },
            "consumed_credit": 30,
            "progress": 100,
        }

    def download_url(self, url: str, destination: Path):
        self.downloaded_url = url
        destination.write_bytes(b"fake-glb")
        return destination


def _request(output_dir: Path, **extras) -> TextTo3DRequest:
    return TextTo3DRequest(
        prompt="weathered sci-fi supply crate",
        negative_prompt="blurry",
        output_dir=output_dir,
        seed=123,
        extras=extras,
    )


def test_tripo_api_probe_requires_key(monkeypatch):
    monkeypatch.delenv("GHOSTFORGE_TRIPO_API_KEY", raising=False)
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)

    probe = TripoAPIWorker().probe()

    assert probe.runnable is False
    assert "GHOSTFORGE_TRIPO_API_KEY" in probe.missing
    assert "TRIPO_API_KEY" in probe.missing
    assert "secret-value" not in json.dumps(probe.model_dump(mode="json"))


def test_tripo_api_probe_reports_hosted_worker_without_secret(monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_TRIPO_API_KEY", "secret-value")

    worker = TripoAPIWorker()
    probe = worker.probe()

    assert Capability.text_to_3d in worker.capabilities
    assert probe.runnable is True
    assert probe.device == "hosted-api"
    payload = json.dumps(probe.model_dump(mode="json"))
    assert "secret-value" not in payload
    assert probe.metadata["selected_api_key_env"] == "GHOSTFORGE_TRIPO_API_KEY"


def test_tripo_api_run_submits_h3_payload_and_downloads_model(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_TRIPO_API_KEY", "secret-value")
    fake = _FakeTripoClient()
    worker = TripoAPIWorker(client=fake)

    result = worker.run(
        _request(
            tmp_path,
            texture=True,
            pbr=True,
            smart_low_poly=True,
            quad=True,
            face_limit=8000,
            export_uv=True,
            geometry_quality="standard",
        ),
        reporter=None,
        cancel=None,
    )

    assert fake.payload is not None
    assert fake.payload["type"] == "text_to_model"
    assert fake.payload["model_version"] == DEFAULT_MODEL_VERSION
    assert fake.payload["model_seed"] == 123
    assert fake.payload["negative_prompt"] == "blurry"
    assert fake.payload["smart_low_poly"] is True
    assert fake.payload["quad"] is True
    assert fake.payload["face_limit"] == 8000
    assert fake.downloaded_url == "https://example.invalid/task-123.glb"
    assert Path(result["output_mesh"]).exists()
    assert result["metadata"]["task_id"] == "task-123"
    assert result["metadata"]["output_field"] == "pbr_model"
    assert "secret-value" not in json.dumps(result)


def test_tripo_api_rejects_inline_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_TRIPO_API_KEY", "secret-value")
    worker = TripoAPIWorker(client=_FakeTripoClient())
    request = _request(tmp_path, api_key="inline-secret")

    with pytest.raises(WorkerUnavailable, match="environment"):
        worker.run(request, reporter=None, cancel=None)
