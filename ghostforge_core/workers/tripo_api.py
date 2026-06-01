"""Hosted Tripo AI text-to-3D worker.

This worker wraps Tripo's OpenAPI task flow behind the same Ghost Forge
worker contract as local GPU models. Secrets are read from environment
variables only; request extras and manifests must never contain API keys.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import CPU_ONLY_RESOURCES
from .schemas import TextTo3DRequest


DEFAULT_API_BASE = "https://api.tripo3d.ai/v2/openapi"
DEFAULT_MODEL_VERSION = "v3.1-20260211"
API_KEY_ENV_NAMES = ("GHOSTFORGE_TRIPO_API_KEY", "TRIPO_API_KEY")
TRIPO_DOCS_URL = "https://platform.tripo3d.ai/docs/introduction"

_FINAL_FAILURE_STATUSES = {"failed", "banned", "expired", "cancelled", "unknown"}
_MODEL_OUTPUT_FIELDS = ("pbr_model", "model", "base_model")
_SUPPORTED_TEXT_OPTIONS = {
    "model_version",
    "image_seed",
    "model_seed",
    "texture",
    "texture_seed",
    "texture_quality",
    "pbr",
    "smart_low_poly",
    "quad",
    "face_limit",
    "auto_size",
    "compress",
    "generate_parts",
    "export_uv",
    "geometry_quality",
}
_SECRET_EXTRA_KEYS = {
    "api_key",
    "apikey",
    "tripo_api_key",
    "tripo_key",
    "authorization",
    "bearer",
    "token",
}


class TripoAPIError(WorkerUnavailable):
    """Raised when the hosted Tripo API declines or fails a task."""


class TripoAPIClient:
    """Small stdlib HTTP client for Tripo's async task API."""

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str = DEFAULT_API_BASE,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 2.0,
        max_wait_seconds: float = 1800.0,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.max_wait_seconds = max_wait_seconds

    def submit_text_to_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "/task", payload)

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/task/{task_id}", None)

    def wait_for_task(
        self,
        task_id: str,
        *,
        reporter: Any = None,
        cancel: Any = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.max_wait_seconds
        while True:
            cancel and cancel.throw_if_cancelled()
            task = self.get_task(task_id)
            status = str(task.get("status") or "").lower()
            progress = task.get("progress")
            if reporter and progress is not None:
                try:
                    reporter(
                        f"tripo:task.{status or 'poll'}",
                        float(progress),
                        f"Tripo task {task_id}: {status or 'polling'}",
                    )
                except Exception:
                    pass
            if status == "success":
                return task
            if status in _FINAL_FAILURE_STATUSES:
                message = task.get("message") or task.get("error") or status
                raise TripoAPIError(f"Tripo task {task_id} ended with status={status}: {message}")
            if time.monotonic() >= deadline:
                raise TripoAPIError(
                    f"Timed out waiting for Tripo task {task_id} after "
                    f"{self.max_wait_seconds:.0f}s"
                )
            time.sleep(max(0.25, self.poll_interval_seconds))

    def download_url(self, url: str, destination: Path) -> Path:
        request = Request(url, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                destination.write_bytes(response.read())
        except (HTTPError, URLError, TimeoutError) as exc:
            raise TripoAPIError(f"failed to download Tripo model: {exc}") from exc
        return destination

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        body = None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.api_base}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TripoAPIError(f"Tripo HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise TripoAPIError(f"Tripo request failed: {exc}") from exc

        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TripoAPIError("Tripo returned non-JSON response") from exc

        code = envelope.get("code", 0)
        if code != 0:
            message = envelope.get("message") or "Tripo API error"
            suggestion = envelope.get("suggestion")
            if suggestion:
                message = f"{message}; suggestion: {suggestion}"
            raise TripoAPIError(f"Tripo API code {code}: {message}")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise TripoAPIError("Tripo response did not contain a data object")
        return data


class TripoAPIWorker:
    """Tripo hosted text-to-3D worker with smart mesh options."""

    name = "tripo_api"
    capabilities = [Capability.text_to_3d]
    priority = 85
    license = "Tripo AI API Terms"
    description = (
        "Hosted Tripo AI text-to-model generation. Uses Tripo OpenAPI H3 "
        "with texture, PBR, smart low-poly, quad, face-limit, UV, and "
        "geometry-quality options when supplied in request extras."
    )
    homepage = TRIPO_DOCS_URL
    paper_url = None
    weights_url = None
    is_stub = False
    resources = CPU_ONLY_RESOURCES
    required_models: list[str] = []

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def probe(self) -> ProbeResult:
        env_name, _api_key = _api_key_from_env(API_KEY_ENV_NAMES)
        metadata = {
            "provider": "tripo",
            "api_base": DEFAULT_API_BASE,
            "docs_url": TRIPO_DOCS_URL,
            "default_model_version": DEFAULT_MODEL_VERSION,
            "api_key_env": list(API_KEY_ENV_NAMES),
            "supports": {
                "texture": True,
                "pbr": True,
                "smart_low_poly": True,
                "quad": True,
                "face_limit": True,
                "auto_size": True,
                "export_uv": True,
                "geometry_quality": True,
            },
        }
        if env_name is None:
            return ProbeResult(
                name=self.name,
                runnable=False,
                reason=(
                    "missing Tripo API key. Set GHOSTFORGE_TRIPO_API_KEY "
                    "or TRIPO_API_KEY in the server environment."
                ),
                missing=list(API_KEY_ENV_NAMES),
                device="hosted-api",
                metadata=metadata,
            )
        return ProbeResult(
            name=self.name,
            runnable=True,
            device="hosted-api",
            metadata={**metadata, "selected_api_key_env": env_name},
        )

    def run(
        self,
        spec: TextTo3DRequest,
        reporter: Any,
        cancel: Any,
    ) -> dict[str, Any]:
        _reject_inline_secrets(spec.extras)
        env_names = _env_names_from_extras(spec.extras)
        env_name, api_key = _api_key_from_env(env_names)
        if not api_key:
            raise WorkerUnavailable(
                "Tripo API key is required. Set GHOSTFORGE_TRIPO_API_KEY "
                "or TRIPO_API_KEY before running tripo_api."
            )

        if reporter:
            reporter("tripo:submit", 2.0, "submitting Tripo text-to-model task")
        cancel and cancel.throw_if_cancelled()

        payload = _build_text_payload(spec)
        client = self._client or TripoAPIClient(
            api_key=api_key,
            api_base=str(spec.extras.get("api_base") or DEFAULT_API_BASE),
            timeout_seconds=float(spec.extras.get("timeout_seconds") or 30.0),
            poll_interval_seconds=float(spec.extras.get("poll_interval_seconds") or 2.0),
            max_wait_seconds=float(spec.extras.get("max_wait_seconds") or 1800.0),
        )
        submit = client.submit_text_to_model(payload)
        task_id = str(submit.get("task_id") or "")
        if not task_id:
            raise TripoAPIError("Tripo submit response did not include task_id")

        if reporter:
            reporter("tripo:poll", 5.0, f"polling Tripo task {task_id}")
        task = client.wait_for_task(task_id, reporter=reporter, cancel=cancel)
        output_field, model_url = _select_model_url(task, wants_pbr=bool(payload.get("pbr", True)))
        out_dir = Path(spec.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = _unique_output_path(
            out_dir,
            f"tripo_{task_id}",
            _extension_for_output(model_url, spec.output_format, quad=bool(payload.get("quad"))),
        )

        if reporter:
            reporter("tripo:download", 95.0, f"downloading {output_field}")
        client.download_url(model_url, out_path)
        cancel and cancel.throw_if_cancelled()
        if reporter:
            reporter("tripo:done", 100.0, "done")

        option_echo = {key: value for key, value in payload.items() if key in _SUPPORTED_TEXT_OPTIONS}
        return {
            "worker": self.name,
            "output_mesh": str(out_path),
            "metadata": {
                "provider": "tripo",
                "task_id": task_id,
                "status": task.get("status"),
                "model_version": payload.get("model_version"),
                "api_base": getattr(client, "api_base", DEFAULT_API_BASE),
                "api_key_env": env_name,
                "output_field": output_field,
                "consumed_credit": task.get("consumed_credit"),
                "options": option_echo,
            },
        }


def _api_key_from_env(env_names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in env_names:
        value = os.environ.get(name)
        if value:
            return name, value
    return None, None


def _env_names_from_extras(extras: dict[str, Any]) -> tuple[str, ...]:
    custom = extras.get("api_key_env")
    if isinstance(custom, str) and custom.strip():
        return (custom.strip(),) + tuple(n for n in API_KEY_ENV_NAMES if n != custom.strip())
    if isinstance(custom, list):
        names = [str(item).strip() for item in custom if str(item).strip()]
        return tuple(names + [n for n in API_KEY_ENV_NAMES if n not in names])
    return API_KEY_ENV_NAMES


def _reject_inline_secrets(extras: dict[str, Any]) -> None:
    for key in extras:
        normalized = key.lower().replace("-", "_")
        if normalized in _SECRET_EXTRA_KEYS:
            raise WorkerUnavailable(
                "Do not pass Tripo API keys in request extras. Set "
                "GHOSTFORGE_TRIPO_API_KEY or TRIPO_API_KEY in the server "
                "environment so manifests and job specs stay secret-free."
            )


def _build_text_payload(spec: TextTo3DRequest) -> dict[str, Any]:
    extras = dict(spec.extras or {})
    payload: dict[str, Any] = {
        "type": "text_to_model",
        "prompt": spec.prompt,
        "model_version": extras.get("model_version") or DEFAULT_MODEL_VERSION,
    }
    if spec.negative_prompt:
        payload["negative_prompt"] = spec.negative_prompt
    if spec.seed is not None and "model_seed" not in extras:
        payload["model_seed"] = int(spec.seed)
    for key in _SUPPORTED_TEXT_OPTIONS:
        if key in extras and extras[key] is not None:
            payload[key] = extras[key]
    return payload


def _select_model_url(task: dict[str, Any], *, wants_pbr: bool) -> tuple[str, str]:
    output = task.get("output")
    if not isinstance(output, dict):
        raise TripoAPIError("Tripo task did not include output URLs")
    preferred = _MODEL_OUTPUT_FIELDS if wants_pbr else ("model", "base_model", "pbr_model")
    for field in preferred:
        value = output.get(field)
        if isinstance(value, str) and value:
            return field, value
    raise TripoAPIError(
        "Tripo task output did not include a downloadable model URL "
        f"(checked: {', '.join(_MODEL_OUTPUT_FIELDS)})"
    )


def _extension_for_output(url: str, requested_format: str, *, quad: bool) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".glb", ".gltf", ".fbx", ".obj", ".stl", ".zip", ".usdz"}:
        return suffix
    if quad:
        return ".fbx"
    requested = (requested_format or "glb").strip().lower().lstrip(".")
    return f".{requested or 'glb'}"


def _unique_output_path(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise TripoAPIError(f"could not allocate output path under {directory}")


__all__ = [
    "API_KEY_ENV_NAMES",
    "DEFAULT_API_BASE",
    "DEFAULT_MODEL_VERSION",
    "TRIPO_DOCS_URL",
    "TripoAPIClient",
    "TripoAPIError",
    "TripoAPIWorker",
]
