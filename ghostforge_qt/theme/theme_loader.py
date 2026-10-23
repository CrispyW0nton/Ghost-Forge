from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from .theme_model import COLOR_ALIASES, METRIC_ALIASES, Theme
from .theme_validator import ThemeValidator, canonical_metric_name, is_hex_color


class ThemeLoader:
    """Load Ghost Forge themes from simple JSON or XML files.

    XML support intentionally mirrors the useful part of Ghost Rigger's theme
    files: metadata, color entries, metric entries, and style entries.
    """

    def __init__(self, validator: ThemeValidator | None = None) -> None:
        self.validator = validator or ThemeValidator()

    def load_file(self, path: Path, *, base_theme: Theme | None = None) -> Theme | None:
        path = Path(path)
        if path.suffix.lower() == ".json":
            return self._load_json(path, base_theme=base_theme)
        if path.suffix.lower() == ".xml":
            return self._load_xml(path, base_theme=base_theme)
        return None

    def load_dir(self, directory: Path, *, base_theme: Theme | None = None) -> dict[str, Theme]:
        themes: dict[str, Theme] = {}
        directory = Path(directory)
        if not directory.exists():
            return themes
        for path in sorted([*directory.glob("*.json"), *directory.glob("*.xml")]):
            theme = self.load_file(path, base_theme=base_theme)
            if theme is not None and theme.id:
                themes[theme.id] = theme
        return themes

    def _load_json(self, path: Path, *, base_theme: Theme | None) -> Theme:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return _invalid_theme(path, f"Could not parse theme JSON: {exc}", base_theme=base_theme)
        if not isinstance(raw, dict):
            return _invalid_theme(path, "Theme JSON root must be an object.", base_theme=base_theme)
        return self._theme_from_payload(raw, path=path, base_theme=base_theme)

    def _load_xml(self, path: Path, *, base_theme: Theme | None) -> Theme:
        try:
            root = ET.parse(path).getroot()
        except Exception as exc:
            return _invalid_theme(path, f"Could not parse theme XML: {exc}", base_theme=base_theme)
        if root.tag != "theme":
            return _invalid_theme(path, "Root element must be <theme>.", base_theme=base_theme)

        metadata = root.find("metadata")
        payload: dict[str, object] = {
            "id": (root.get("id") or path.stem).strip(),
            "name": (root.get("name") or path.stem).strip(),
            "version": (root.get("version") or "1.0").strip(),
            "mode": ((metadata.findtext("mode") if metadata is not None else None) or "dark").strip(),
            "description": ((metadata.findtext("description") if metadata is not None else None) or "").strip(),
            "colors": {
                (entry.get("name") or "").strip(): (entry.get("value") or "").strip()
                for entry in root.findall("./colors/color")
            },
            "metrics": {
                (entry.get("name") or "").strip(): (entry.get("value") or "").strip()
                for entry in root.findall("./metrics/metric")
            },
            "styles": {
                (entry.get("name") or "").strip(): (entry.get("value") or "").strip()
                for entry in root.findall("./styles/style")
            },
        }
        return self._theme_from_payload(payload, path=path, base_theme=base_theme)

    def _theme_from_payload(self, payload: dict[str, object], *, path: Path, base_theme: Theme | None) -> Theme:
        warnings = self.validator.validate_payload(payload, source=path.name)
        fallback = base_theme or Theme(
            id="fallback",
            name="Fallback",
            colors={},
            metrics={},
        )
        theme_id = str(payload.get("id") or path.stem).strip() or path.stem
        name = str(payload.get("name") or theme_id).strip() or theme_id
        colors = dict(fallback.colors)
        colors.update(_valid_color_items(payload.get("colors"), warnings=warnings, source=path.name))
        metrics = dict(fallback.metrics)
        metrics.update(_valid_metric_items(payload.get("metrics"), warnings=warnings, source=path.name))
        styles = dict(fallback.styles)
        styles.update(_string_items(payload.get("styles")))
        return Theme(
            id=theme_id,
            name=name,
            version=str(payload.get("version") or "1.0").strip() or "1.0",
            mode=str(payload.get("mode") or fallback.mode or "dark").strip().lower(),
            description=str(payload.get("description") or "").strip(),
            colors=colors,
            metrics=metrics,
            styles=styles,
            warnings=tuple(warnings),
            source_path=str(path),
        )


def _valid_color_items(value: object, *, warnings: list[str], source: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(value, dict):
        return out
    for key, raw in value.items():
        token = str(key or "").strip()
        color = str(raw or "").strip()
        if not token or not is_hex_color(color):
            continue
        out[token] = color
        alias = COLOR_ALIASES.get(token, "")
        if alias:
            out.setdefault(alias, color)
    return out


def _valid_metric_items(value: object, *, warnings: list[str], source: str) -> dict[str, int]:
    out: dict[str, int] = {}
    if not isinstance(value, dict):
        return out
    for key, raw in value.items():
        token = str(key or "").strip()
        try:
            metric = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if not token or metric < 0:
            continue
        out[canonical_metric_name(token)] = metric
    return out


def _string_items(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key).strip(): str(raw).strip() for key, raw in value.items() if str(key).strip()}


def _invalid_theme(path: Path, warning: str, *, base_theme: Theme | None) -> Theme:
    fallback = base_theme or Theme(id="fallback", name="Fallback", colors={}, metrics={})
    return Theme(
        id=path.stem,
        name=path.stem,
        version="invalid",
        mode=fallback.mode,
        description="Invalid theme file.",
        colors=dict(fallback.colors),
        metrics=dict(fallback.metrics),
        styles=dict(fallback.styles),
        warnings=(f"{path.name}: {warning}",),
        source_path=str(path),
    )
