from __future__ import annotations

from dataclasses import dataclass
import re

from .theme_model import COLOR_ALIASES, METRIC_ALIASES, Theme

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")

RECOMMENDED_COLOR_TOKENS = (
    "window.bg",
    "panel.bg",
    "panel.alt",
    "panel.border",
    "viewport.bg",
    "viewport.grid",
    "viewport.grid.major",
    "text.primary",
    "text.secondary",
    "accent.primary",
    "button.bg",
    "button.hover",
    "input.bg",
    "selection.bg",
)

CONTRAST_CHECKS = (
    ("text.primary", "window.bg", 4.5, "Primary text must be readable on the main window."),
    ("text.primary", "panel.bg", 4.5, "Primary text must be readable on dock panels."),
    ("text.primary", "panel.alt", 4.5, "Primary text must be readable on alternate panels."),
    ("text.secondary", "panel.bg", 3.0, "Secondary text must remain readable on dock panels."),
    ("text.primary", "input.bg", 4.5, "Input text must be readable in fields."),
    ("text.primary", "button.bg", 4.5, "Button text must be readable on button backgrounds."),
    ("accent.primary", "viewport.bg", 2.5, "Viewport accent overlays need visible separation from the canvas."),
    ("viewport.grid.major", "viewport.bg", 1.5, "Major grid lines need visible separation from the canvas."),
)


def is_hex_color(value: object) -> bool:
    return bool(_HEX_COLOR_RE.match(str(value or "").strip()))


@dataclass(frozen=True)
class ThemeDiagnostic:
    severity: str
    code: str
    message: str
    foreground_token: str = ""
    background_token: str = ""
    ratio: float | None = None
    minimum: float | None = None

    def as_warning(self) -> str:
        return self.message


class ThemeValidator:
    """Non-fatal theme validation for file-loaded Ghost Forge themes."""

    def validate_payload(self, payload: dict[str, object], *, source: str = "") -> list[str]:
        warnings: list[str] = []
        if not str(payload.get("id") or "").strip():
            warnings.append("Theme is missing required field 'id'.")
        if not str(payload.get("name") or "").strip():
            warnings.append("Theme is missing required field 'name'.")

        colors = payload.get("colors")
        if colors is not None and not isinstance(colors, dict):
            warnings.append("Theme field 'colors' must be an object.")
        if isinstance(colors, dict):
            seen = set()
            for key, value in colors.items():
                token = str(key or "").strip()
                if not token:
                    warnings.append("A color entry is missing its token name.")
                    continue
                seen.add(token)
                if not is_hex_color(value):
                    warnings.append(f"Color '{token}' has invalid value '{value}'.")
            for token in RECOMMENDED_COLOR_TOKENS:
                alias = next((name for name, target in COLOR_ALIASES.items() if target == token), "")
                if token not in seen and alias not in seen:
                    warnings.append(f"Theme is missing recommended color token '{token}'; fallback will be used.")

        metrics = payload.get("metrics")
        if metrics is not None and not isinstance(metrics, dict):
            warnings.append("Theme field 'metrics' must be an object.")
        if isinstance(metrics, dict):
            for key, value in metrics.items():
                token = str(key or "").strip()
                try:
                    metric_value = int(value)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    warnings.append(f"Metric '{token}' must be an integer.")
                    continue
                if metric_value < 0 or metric_value > 5000:
                    warnings.append(f"Metric '{token}' has suspicious value '{metric_value}'.")

        styles = payload.get("styles")
        if styles is not None and not isinstance(styles, dict):
            warnings.append("Theme field 'styles' must be an object.")

        if source:
            warnings = [f"{source}: {warning}" for warning in warnings]
        return warnings

    def validate_theme(self, theme: Theme) -> list[str]:
        payload: dict[str, object] = {
            "id": theme.id,
            "name": theme.name,
            "colors": theme.colors,
            "metrics": theme.metrics,
            "styles": theme.styles,
        }
        return [
            *theme.warnings,
            *self.validate_payload(payload),
            *(diagnostic.as_warning() for diagnostic in self.accessibility_diagnostics(theme)),
        ]

    def accessibility_diagnostics(self, theme: Theme) -> list[ThemeDiagnostic]:
        diagnostics: list[ThemeDiagnostic] = []
        for foreground, background, minimum, reason in CONTRAST_CHECKS:
            ratio = contrast_ratio(theme.color(foreground), theme.color(background))
            if ratio is None:
                continue
            if ratio < minimum:
                diagnostics.append(
                    ThemeDiagnostic(
                        severity="warning",
                        code="contrast.low",
                        foreground_token=foreground,
                        background_token=background,
                        ratio=ratio,
                        minimum=minimum,
                        message=(
                            f"Contrast warning: {foreground} on {background} is "
                            f"{ratio:.2f}:1; expected at least {minimum:.2f}:1. {reason}"
                        ),
                    )
                )
        return diagnostics


def canonical_metric_name(token: str) -> str:
    return METRIC_ALIASES.get(token, token)


def contrast_ratio(foreground: object, background: object) -> float | None:
    fg = _hex_to_rgb(foreground)
    bg = _hex_to_rgb(background)
    if fg is None or bg is None:
        return None
    fg_luminance = _relative_luminance(fg)
    bg_luminance = _relative_luminance(bg)
    lighter = max(fg_luminance, bg_luminance)
    darker = min(fg_luminance, bg_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _hex_to_rgb(value: object) -> tuple[int, int, int] | None:
    text = str(value or "").strip()
    if not is_hex_color(text):
        return None
    return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = (_linear_channel(channel / 255.0) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _linear_channel(channel: float) -> float:
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4
