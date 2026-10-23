from __future__ import annotations

from dataclasses import dataclass, field


COLOR_ALIASES = {
    "window.background": "window.bg",
    "panel.background": "panel.bg",
    "panel.backgroundAlt": "panel.alt",
    "panel.altBackground": "panel.alt",
    "panel.border": "panel.border",
    "toolbar.background": "panel.bg",
    "toolbar.border": "panel.border",
    "viewport.background": "viewport.bg",
    "viewport.grid": "viewport.grid",
    "viewport.gridMajor": "viewport.grid.major",
    "viewportToolbar.background": "panel.alt",
    "viewportToolbar.border": "panel.border",
    "text.primary": "text.primary",
    "text.secondary": "text.secondary",
    "text.muted": "text.muted",
    "selection.background": "selection.bg",
    "button.background": "button.bg",
    "button.hover": "button.hover",
    "button.checked": "button.checked",
    "input.background": "input.bg",
}

METRIC_ALIASES = {
    "panel.margin": "panel_margin",
    "panel.spacing": "panel_spacing",
    "toolbar.height": "toolbar_height",
    "input.height": "input_height",
    "dock.titleHeight": "dock_title_height",
}


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    colors: dict[str, str]
    metrics: dict[str, int]
    mode: str = "dark"
    description: str = ""
    version: str = "1.0"
    styles: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    source_path: str = ""

    def color(self, token: str, default: str = "#000000") -> str:
        alias = COLOR_ALIASES.get(token, "")
        return self.colors.get(token) or (self.colors.get(alias) if alias else None) or default

    def metric(self, token: str, default: int = 0) -> int:
        alias = METRIC_ALIASES.get(token, "")
        return int(self.metrics.get(token) or (self.metrics.get(alias) if alias else None) or default)

    def style(self, token: str, default: str = "") -> str:
        return str(self.styles.get(token, default))


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
        mode="dark",
        description="Production dark theme tuned for modeling and AI pipeline panels.",
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
        mode="light",
        description="Light studio theme for readable documentation, manifests, and tables.",
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
    graphite = Theme(
        id="graphite_studio",
        name="Graphite Studio",
        metrics={**base_metrics, "panel_spacing": 5, "toolbar_height": 30},
        mode="dark",
        description="Neutral DCC-style theme inspired by Ghost Rigger's dense production layouts.",
        colors={
            "window.bg": "#121417",
            "panel.bg": "#1c2025",
            "panel.alt": "#252a30",
            "panel.border": "#3b444d",
            "viewport.bg": "#0b0d10",
            "viewport.grid": "#27303a",
            "viewport.grid.major": "#475462",
            "text.primary": "#e6edf3",
            "text.secondary": "#b3c0ca",
            "text.muted": "#7d8994",
            "accent.primary": "#f2b84b",
            "accent.secondary": "#6fb4e8",
            "accent.warning": "#f2b84b",
            "accent.danger": "#df6a6a",
            "button.bg": "#242a31",
            "button.hover": "#303842",
            "button.checked": "#3d3521",
            "input.bg": "#15191e",
            "selection.bg": "#35485c",
        },
    )
    ghost_rigger_dark = Theme(
        id="ghost_rigger_dark",
        name="Ghost Rigger Dark",
        metrics={
            **base_metrics,
            "panel_margin": 5,
            "panel_spacing": 5,
            "toolbar_height": 28,
            "input_height": 24,
            "dock_title_height": 22,
            "button.height": 24,
            "button.minWidth": 70,
            "tab.height": 18,
            "tab.width": 74,
            "tab.paddingX": 9,
            "tab.paddingY": 4,
            "statusbar.height": 22,
            "border.radius": 3,
        },
        mode="dark",
        description="Dense production editor theme adapted from Ghost Rigger's dark Qt shell.",
        colors={
            "window.bg": "#151515",
            "window.background": "#151515",
            "panel.bg": "#202020",
            "panel.background": "#202020",
            "panel.alt": "#2b2b2b",
            "panel.backgroundAlt": "#2b2b2b",
            "panel.border": "#3d3d3d",
            "panel.headerBackground": "#252525",
            "panel.headerText": "#f0f0f0",
            "toolbar.background": "#2a2a2a",
            "toolbar.border": "#3f3f3f",
            "viewport.bg": "#1b1d1f",
            "viewport.background": "#1b1d1f",
            "viewport.border": "#32383f",
            "viewport.text": "#dbe7f2",
            "viewport.grid": "#363d44",
            "viewport.grid.major": "#515b66",
            "viewportToolbar.background": "#303030",
            "viewportToolbar.border": "#4a4a4a",
            "table.background": "#1f1f1f",
            "table.text": "#eeeeee",
            "table.headerBackground": "#30343a",
            "table.headerText": "#f2f2f2",
            "table.grid": "#42474d",
            "tree.background": "#1f1f1f",
            "tree.text": "#eeeeee",
            "tab.background": "#292929",
            "tab.text": "#bfc8d2",
            "tab.selectedBackground": "#1f1f1f",
            "tab.selectedText": "#ffffff",
            "groupbox.border": "#444a50",
            "groupbox.title": "#d7e2ef",
            "text.primary": "#f1f1f1",
            "text.secondary": "#b9c4cc",
            "text.muted": "#7f8992",
            "text.disabled": "#686868",
            "accent.primary": "#58d68d",
            "accent.secondary": "#5dade2",
            "accent.warning": "#f0b650",
            "accent.danger": "#e57373",
            "button.bg": "#303030",
            "button.background": "#303030",
            "button.text": "#f0f0f0",
            "button.hover": "#3a4148",
            "button.pressed": "#232323",
            "button.checked": "#304737",
            "button.checkedText": "#ffffff",
            "button.accentText": "#101010",
            "button.disabledBackground": "#252525",
            "button.disabledText": "#737373",
            "input.bg": "#1b1b1b",
            "input.background": "#1b1b1b",
            "input.text": "#f2f2f2",
            "input.border": "#4a5158",
            "input.focusBorder": "#5dade2",
            "selection.bg": "#2f5d76",
            "selection.background": "#2f5d76",
            "selection.text": "#ffffff",
            "scrollbar.background": "#202020",
            "scrollbar.handle": "#4a4f54",
        },
        styles={
            "tab.mode": "flat",
            "application.palette": "true",
        },
    )
    return {theme.id: theme for theme in (forge_dark, studio_light, graphite, ghost_rigger_dark)}
