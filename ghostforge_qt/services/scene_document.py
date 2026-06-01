from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ghostforge_core.authoring import EditGraph
from ghostforge_core.types import utc_now
from ghostforge_qt.models.scene_model import SceneObjectRecord, TransformState


SCENE_DOCUMENT_VERSION = "1.0"
SCENE_DOCUMENT_EXTENSION = ".gforge"


@dataclass(frozen=True)
class SceneDocument:
    path: Path
    project_root: Path
    records: list[SceneObjectRecord]
    saved_at: str
    units: str = "meters"
    up_axis: str = "Y"
    forward_axis: str = "-Z"


class SceneDocumentService:
    """Versioned `.gforge` scene persistence for the Qt editor."""

    def default_scene_path(self, project_root: Path, name: str = "untitled") -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name).strip("_")
        stem = safe_name or "untitled"
        return Path(project_root).resolve() / "scenes" / f"{stem}{SCENE_DOCUMENT_EXTENSION}"

    def write(
        self,
        path: Path,
        *,
        project_root: Path,
        records: list[SceneObjectRecord],
        units: str = "meters",
        up_axis: str = "Y",
        forward_axis: str = "-Z",
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "document_version": SCENE_DOCUMENT_VERSION,
            "application": "Ghost Forge",
            "saved_at": utc_now().isoformat(),
            "project_root": str(Path(project_root).resolve()),
            "coordinate_policy": {
                "units": units,
                "up_axis": up_axis,
                "forward_axis": forward_axis,
            },
            "objects": [_record_to_dict(record) for record in records],
        }
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return target

    def read(self, path: Path) -> SceneDocument:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        version = payload.get("document_version")
        if version != SCENE_DOCUMENT_VERSION:
            raise ValueError(f"Unsupported scene document version: {version!r}")

        policy = payload.get("coordinate_policy") or {}
        project_root = Path(payload.get("project_root") or source.parent.parent).resolve()
        objects = payload.get("objects")
        if not isinstance(objects, list):
            raise ValueError("Scene document is missing an objects list")

        return SceneDocument(
            path=source,
            project_root=project_root,
            records=[_record_from_dict(item) for item in objects],
            saved_at=str(payload.get("saved_at") or ""),
            units=str(policy.get("units") or "meters"),
            up_axis=str(policy.get("up_axis") or "Y"),
            forward_axis=str(policy.get("forward_axis") or "-Z"),
        )


def _record_to_dict(record: SceneObjectRecord) -> dict[str, Any]:
    return {
        "object_id": record.object_id,
        "name": record.name,
        "path": str(record.path),
        "asset_dir": None if record.asset_dir is None else str(record.asset_dir),
        "manifest_path": None if record.manifest_path is None else str(record.manifest_path),
        "visible": record.visible,
        "vertices": record.vertices,
        "faces": record.faces,
        "watertight": record.watertight,
        "transform": _transform_to_dict(record.transform),
        "operations": list(record.operations),
        "operation_graph": _graph_to_dict(record.operation_graph),
    }


def _record_from_dict(payload: dict[str, Any]) -> SceneObjectRecord:
    if not isinstance(payload, dict):
        raise ValueError("Scene object entries must be objects")
    return SceneObjectRecord(
        object_id=str(payload["object_id"]),
        name=str(payload.get("name") or Path(str(payload["path"])).stem),
        path=Path(str(payload["path"])),
        asset_dir=_optional_path(payload.get("asset_dir")),
        manifest_path=_optional_path(payload.get("manifest_path")),
        vertices=_optional_int(payload.get("vertices")),
        faces=_optional_int(payload.get("faces")),
        watertight=_optional_bool(payload.get("watertight")),
        visible=bool(payload.get("visible", True)),
        transform=_transform_from_dict(payload.get("transform") or {}),
        operations=tuple(str(item) for item in payload.get("operations") or ()),
        operation_graph=_graph_from_dict(payload.get("operation_graph")),
    )


def _graph_to_dict(graph: EditGraph | None) -> dict[str, Any] | None:
    if graph is None:
        return None
    return graph.model_dump(mode="json")


def _graph_from_dict(payload: Any) -> EditGraph | None:
    if payload in (None, ""):
        return None
    if not isinstance(payload, dict):
        raise ValueError("operation_graph must be an object")
    return EditGraph.model_validate(payload)


def _transform_to_dict(transform: TransformState) -> dict[str, list[float]]:
    return {
        "translate": [float(v) for v in transform.translate],
        "rotate_euler_deg": [float(v) for v in transform.rotate_euler_deg],
        "scale": [float(v) for v in transform.scale],
    }


def _transform_from_dict(payload: dict[str, Any]) -> TransformState:
    return TransformState(
        translate=_triple(payload.get("translate"), (0.0, 0.0, 0.0)),
        rotate_euler_deg=_triple(payload.get("rotate_euler_deg"), (0.0, 0.0, 0.0)),
        scale=_triple(payload.get("scale"), (1.0, 1.0, 1.0)),
    )


def _triple(value: Any, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return default
    return (float(value[0]), float(value[1]), float(value[2]))


def _optional_path(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
