from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    colors: dict[str, str]
    metrics: dict[str, int]

    def color(self, token: str, default: str = "#000000") -> str:
        return self.colors.get(token, default)

    def metric(self, token: str, default: int = 0) -> int:
        return int(self.metrics.get(token, default))


def built_in_themes() -> dict[str, Theme]:
    base_metrics = {
        "panel_margin": 6,
        "panel_spacing": 6,
        "toolbar_height": 32,
        "input_height": 26,
        "dock_title_height": 24,
    }
    forge_dark = Theme(
        id="forge_dark",
        name="Forge Dark",
        metrics=base_metrics,
        colors={
            "window.bg": "#0d1014",
            "panel.bg": "#141920",
            "panel.alt": "#1b222b",
            "panel.border": "#2a3542",
            "viewport.bg": "#070a0d",
            "viewport.grid": "#1d3028",
            "viewport.grid.major": "#2d5c43",
            "text.primary": "#dce7e1",
            "text.secondary": "#9fb0aa",
            "text.muted": "#6c7a78",
            "accent.primary": "#55d47a",
            "accent.secondary": "#4bb9ff",
            "accent.warning": "#f1c15d",
            "accent.danger": "#e36b6b",
            "button.bg": "#1b242c",
            "button.hover": "#25313b",
            "button.checked": "#264b36",
            "input.bg": "#0f1419",
            "selection.bg": "#244f64",
        },
    )
    studio_light = Theme(
        id="studio_light",
        name="Studio Light",
        metrics=base_metrics,
        colors={
            "window.bg": "#f0f2f4",
            "panel.bg": "#ffffff",
            "panel.alt": "#e7ebef",
            "panel.border": "#b9c2cc",
            "viewport.bg": "#dfe5ea",
            "viewport.grid": "#c5cdd5",
            "viewport.grid.major": "#9facba",
            "text.primary": "#1d252d",
            "text.secondary": "#4b5965",
            "text.muted": "#7a8792",
            "accent.primary": "#1f8f58",
            "accent.secondary": "#1f6fb2",
            "accent.warning": "#a26b00",
            "accent.danger": "#b13c3c",
            "button.bg": "#eef1f4",
            "button.hover": "#dde4ea",
            "button.checked": "#cfe8d9",
            "input.bg": "#ffffff",
            "selection.bg": "#b7d7ea",
        },
    )
    return {theme.id: theme for theme in (forge_dark, studio_light)}
