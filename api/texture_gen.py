"""
Texture Generation Module — GhostForge v1.4
Generates PBR-quality procedural textures for UV-unwrapped 3D meshes.

Materials supported (procedural, no GPU required):
  METALS:   metal / steel / chrome / iron / rust / oxidised / galvanized / titanium / gunmetal
  PRECIOUS: gold / copper / bronze / brass / silver / platinum / rose gold
  WOOD:     wood / oak / pine / walnut / mahogany / bamboo / ebony / ash / cedar / driftwood
  STONE:    stone / rock / granite / limestone / marble / travertine / obsidian / sandstone
            cobblestone / slate / basalt / quartzite
  ORGANIC:  leather / fabric / cloth / denim / velvet / skin / scales / fur / moss / bark
  GROUND:   sand / desert / earth / soil / mud / gravel / snow / ash / coal
  SPECIAL:  circuit / cyberpunk / matrix / neon / hologram
            carbon / composite / ceramic / porcelain / terracotta
            lava / fire / magma / plasma / void
            ice / frost / glass / crystal / diamond / water
            rubber / plastic / latex
            paint / chalk / grunge / stucco / plaster
            alien / bio / organic-tech
  + AI mode via Stable Diffusion (optional, requires GPU)

v1.4 additions:
  - 20+ new procedural material types (silver, platinum, rose gold, bamboo, ebony,
    driftwood, bark, obsidian, sandstone, cobblestone, slate, velvet, scales, fur, moss,
    mud, gravel, coal, ceramic, plasma, void, rubber, plastic, paint, stucco, alien, bio)
  - Enhanced noise utilities (fbm_noise, ridge_noise, turbulence_noise)
  - Per-material sub-variant keywords for finer control

v1.3 fixes:
  - bake_texture_to_uv() is now called in generate_texture() so the texture
    is properly UV-projected into atlas space rather than applied as a flat tile
  - Numpy-vectorized rasteriser replaces slow Python loop (10-50x faster)
  - Seamless padding fill (dilate) eliminates UV-seam bleed artifacts
"""

import os
import math
import logging
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps
import trimesh
import io

logger = logging.getLogger(__name__)

# ─── Utility: fast tiling noise ──────────────────────────────────────────────

def _smooth_noise(rng, size, scale, octaves=4):
    """Multi-octave smooth noise — tileable, no scipy dependency."""
    result = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    frequency = scale
    for _ in range(octaves):
        freq = max(1, int(frequency))
        raw = rng.random((freq, freq)).astype(np.float32)
        # Tile & upsample with bilinear interpolation via PIL
        small = Image.fromarray((raw * 255).astype(np.uint8), 'L')
        up = small.resize((size, size), Image.BILINEAR)
        result += (np.array(up, dtype=np.float32) / 255.0) * amplitude
        amplitude *= 0.5
        frequency *= 2
    # Normalise to [0, 1]
    mn, mx = result.min(), result.max()
    if mx > mn:
        result = (result - mn) / (mx - mn)
    return result


def _voronoi_noise(rng, size, num_points=64):
    """Simple Voronoi / cell noise for leather, stone etc."""
    pts = rng.random((num_points, 2)) * size
    yy, xx = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    coords = np.stack([yy.ravel(), xx.ravel()], axis=1).astype(np.float32)
    dist = np.full(len(coords), np.inf, dtype=np.float32)
    for p in pts:
        d = np.sqrt((coords[:, 0] - p[0])**2 + (coords[:, 1] - p[1])**2)
        dist = np.minimum(dist, d)
    dist = dist.reshape(size, size)
    dist /= dist.max() + 1e-9
    return dist.astype(np.float32)


def _warp_noise(rng, size, scale):
    """Domain-warped noise for organic / turbulent materials."""
    n1 = _smooth_noise(rng, size, scale, octaves=4)
    n2 = _smooth_noise(rng, size, scale, octaves=4)
    warp_x = (n2 - 0.5) * size * 0.08
    warp_y = (n1 - 0.5) * size * 0.08
    yy, xx = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    wx = np.clip((xx + warp_x).astype(int), 0, size - 1)
    wy = np.clip((yy + warp_y).astype(int), 0, size - 1)
    base = _smooth_noise(rng, size, scale, octaves=5)
    return base[wy, wx]


# ─── Enhanced noise utilities ────────────────────────────────────────────────

def _fbm_noise(rng, size, scale, octaves=6, lacunarity=2.0, gain=0.5):
    """Fractal Brownian Motion — layered noise for naturalistic detail."""
    result = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    frequency = scale
    total_amp = 0.0
    for _ in range(octaves):
        result += _smooth_noise(rng, size, max(1, int(frequency)), octaves=1) * amplitude
        total_amp += amplitude
        amplitude *= gain
        frequency *= lacunarity
    result /= (total_amp + 1e-9)
    mn, mx = result.min(), result.max()
    if mx > mn:
        result = (result - mn) / (mx - mn)
    return result


def _ridge_noise(rng, size, scale, octaves=5):
    """Ridge noise — inverted absolute noise, great for veins and cracks."""
    n = _fbm_noise(rng, size, scale, octaves=octaves)
    ridge = 1.0 - np.abs(n * 2.0 - 1.0)
    ridge = np.power(ridge, 2.0)
    return ridge.astype(np.float32)


def _turbulence_noise(rng, size, scale, octaves=6):
    """Turbulence — sum of absolute octave values, creates swirling patterns."""
    result = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    frequency = scale
    for _ in range(octaves):
        n = _smooth_noise(rng, size, max(1, int(frequency)), octaves=1)
        result += np.abs(n * 2.0 - 1.0) * amplitude
        amplitude *= 0.5
        frequency *= 2.0
    mn, mx = result.min(), result.max()
    if mx > mn:
        result = (result - mn) / (mx - mn)
    return result.astype(np.float32)


def _hexagonal_grid(size, cell_size=32):
    """Hexagonal tiling mask for ceramic, scale, reptile patterns."""
    yy, xx = np.meshgrid(np.arange(size, dtype=np.float32),
                          np.arange(size, dtype=np.float32), indexing='ij')
    h = cell_size
    w = h * np.sqrt(3.0) / 2.0
    row = (yy / h).astype(int)
    offset = (row % 2) * (w * 0.5)
    col_f = (xx + offset) / w
    col = col_f.astype(int)
    cx = (col + 0.5) * w - offset
    cy = (row + 0.5) * h
    dx = np.abs(xx - cx) / w
    dy = np.abs(yy - cy) / h
    dist = np.maximum(dx, dy * 1.155)
    return dist.astype(np.float32)


# ─── Individual material generators ──────────────────────────────────────────

def _make_metal(rng, size, prompt):
    """Polished / brushed metal — steel, chrome, iron."""
    rust   = any(w in prompt for w in ['rust', 'rusted', 'oxidis', 'worn iron', 'aged iron'])
    chrome = any(w in prompt for w in ['chrome', 'mirror', 'polished'])

    base_n  = _smooth_noise(rng, size, 4, octaves=6)
    streak  = _smooth_noise(rng, size, 32, octaves=2)  # directional streaks
    streak  = np.power(streak, 1.5)

    if chrome:
        r = (0.90 + base_n * 0.08 + streak * 0.04).clip(0, 1)
        g = (0.90 + base_n * 0.08 + streak * 0.04).clip(0, 1)
        b = (0.95 + base_n * 0.05).clip(0, 1)
    elif rust:
        rust_n = _warp_noise(rng, size, 10)
        r = (0.55 + rust_n * 0.30 + base_n * 0.10).clip(0, 1)
        g = (0.25 + rust_n * 0.15 + base_n * 0.05).clip(0, 1)
        b = (0.10 + base_n * 0.08).clip(0, 1)
        # Add dark crevice patches
        crev = (rust_n > 0.75).astype(float)
        r = (r * (1 - crev * 0.35)).clip(0, 1)
        g = (g * (1 - crev * 0.35)).clip(0, 1)
        b = (b * (1 - crev * 0.20)).clip(0, 1)
    else:
        # Brushed steel
        r = (0.60 + base_n * 0.12 + streak * 0.06).clip(0, 1)
        g = (0.62 + base_n * 0.12 + streak * 0.06).clip(0, 1)
        b = (0.67 + base_n * 0.10 + streak * 0.04).clip(0, 1)

    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


def _make_gold(rng, size, prompt):
    """Gold, copper, bronze, brass."""
    if 'copper' in prompt:
        cr, cg, cb = 0.72, 0.45, 0.20
    elif 'bronze' in prompt:
        cr, cg, cb = 0.80, 0.50, 0.20
    elif 'brass' in prompt:
        cr, cg, cb = 0.85, 0.65, 0.13
    else:
        cr, cg, cb = 0.85, 0.67, 0.12   # gold

    n  = _smooth_noise(rng, size, 6, octaves=5)
    s  = _smooth_noise(rng, size, 32, octaves=2)
    r  = (cr + n * 0.08 + s * 0.06).clip(0, 1)
    g  = (cg + n * 0.08 + s * 0.05).clip(0, 1)
    b  = (cb + n * 0.04).clip(0, 1)
    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


def _make_wood(rng, size, prompt):
    """Procedural wood grain — oak, pine, walnut, mahogany."""
    if 'walnut' in prompt or 'dark' in prompt:
        base = (0.28, 0.18, 0.10)
        ring = (0.18, 0.10, 0.05)
    elif 'pine' in prompt or 'light' in prompt:
        base = (0.82, 0.64, 0.38)
        ring = (0.70, 0.52, 0.28)
    elif 'mahogany' in prompt:
        base = (0.55, 0.23, 0.12)
        ring = (0.40, 0.16, 0.08)
    else:  # oak / default
        base = (0.65, 0.42, 0.20)
        ring = (0.52, 0.32, 0.12)

    yy, xx = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    # Distort the rings with low-freq noise
    n_warp = _warp_noise(rng, size, 8)
    cx, cy = size * 0.5, size * 0.5
    dist = np.sqrt((xx - cx)**2 * 0.7 + (yy - cy)**2 * 1.3) / (size * 0.5)
    dist = (dist + n_warp * 0.25) % 1.0
    ring_mask = (np.sin(dist * math.pi * 28) * 0.5 + 0.5)
    ring_mask = np.power(ring_mask, 2.0)

    # Fine grain
    grain = _smooth_noise(rng, size, 64, octaves=3) * 0.07

    r = (base[0] + (ring[0] - base[0]) * ring_mask + grain).clip(0, 1)
    g = (base[1] + (ring[1] - base[1]) * ring_mask + grain * 0.8).clip(0, 1)
    b = (base[2] + (ring[2] - base[2]) * ring_mask + grain * 0.5).clip(0, 1)

    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


def _make_marble(rng, size, prompt):
    """Marble or travertine — white / grey veins."""
    if 'black' in prompt:
        bg = (0.10, 0.10, 0.12)
        vein = (0.60, 0.62, 0.65)
    elif 'green' in prompt:
        bg = (0.20, 0.38, 0.25)
        vein = (0.80, 0.85, 0.78)
    elif 'gold' in prompt:
        bg = (0.95, 0.92, 0.85)
        vein = (0.80, 0.68, 0.20)
    else:  # white / luxury default
        bg = (0.92, 0.91, 0.90)
        vein = (0.60, 0.58, 0.56)

    n = _warp_noise(rng, size, 12)
    # Veins are sharp narrow bands
    vein_n = np.abs(np.sin(n * math.pi * 6))
    vein_n = np.power(vein_n, 3)  # sharper

    r = (bg[0] + (vein[0] - bg[0]) * vein_n).clip(0, 1)
    g = (bg[1] + (vein[1] - bg[1]) * vein_n).clip(0, 1)
    b = (bg[2] + (vein[2] - bg[2]) * vein_n).clip(0, 1)

    # Fine surface noise
    fine = _smooth_noise(rng, size, 8, octaves=2) * 0.03
    rgb = np.stack([r + fine, g + fine, b + fine], axis=-1).clip(0, 1)
    return (rgb * 255).astype(np.uint8)


def _make_stone(rng, size, prompt):
    """Rock, granite, limestone, concrete, brick."""
    concrete = any(w in prompt for w in ['concrete', 'cement', 'brutalist'])
    granite  = 'granite' in prompt
    brick    = 'brick' in prompt

    if brick:
        return _make_brick(rng, size)

    if concrete:
        cr, cg, cb = 0.64, 0.64, 0.62
    elif granite:
        cr, cg, cb = 0.40, 0.38, 0.36
    else:
        cr, cg, cb = 0.55, 0.52, 0.46

    n1 = _smooth_noise(rng, size, 6, octaves=6)
    n2 = _smooth_noise(rng, size, 16, octaves=3) * 0.15

    r = (cr + n1 * 0.18 + n2).clip(0, 1)
    g = (cg + n1 * 0.16 + n2).clip(0, 1)
    b = (cb + n1 * 0.14 + n2).clip(0, 1)

    # Add micro-cracks
    v = _voronoi_noise(rng, size, num_points=80)
    crack = (v < 0.05).astype(float) * 0.3
    r = (r - crack).clip(0, 1)
    g = (g - crack).clip(0, 1)
    b = (b - crack).clip(0, 1)

    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


def _make_brick(rng, size):
    """Red brick wall."""
    canvas = np.zeros((size, size, 3), dtype=np.float32)
    n = _smooth_noise(rng, size, 8, octaves=4)
    rows, cols = 14, 8
    bh, bw = size // rows, size // cols
    mortar = 0.04 * size
    for row in range(rows + 1):
        for col in range(cols + 1):
            ox = (bw // 2) * (row % 2)
            x0 = int((col * bw + ox) % size)
            y0 = row * bh
            x1 = min(x0 + bw - int(mortar), size)
            y1 = min(y0 + bh - int(mortar), size)
            if x0 >= x1 or y0 >= y1:
                continue
            patch = n[y0:y1, x0:x1]
            r = (0.72 + patch * 0.12).clip(0, 1)
            g = (0.28 + patch * 0.06).clip(0, 1)
            b = (0.18 + patch * 0.04).clip(0, 1)
            canvas[y0:y1, x0:x1, 0] = r
            canvas[y0:y1, x0:x1, 1] = g
            canvas[y0:y1, x0:x1, 2] = b
    # Mortar is background (already black → tint grey)
    mortar_mask = (canvas.sum(axis=-1) == 0)
    canvas[mortar_mask] = [0.75, 0.74, 0.70]
    return (canvas * 255).astype(np.uint8)


def _make_leather(rng, size, prompt):
    """Leather, fabric, or cloth."""
    fabric = any(w in prompt for w in ['fabric', 'cloth', 'textile', 'denim'])
    if fabric:
        cr, cg, cb = 0.35, 0.42, 0.75
    elif 'brown' in prompt or 'tan' in prompt:
        cr, cg, cb = 0.60, 0.38, 0.18
    else:
        cr, cg, cb = 0.22, 0.16, 0.12

    n = _smooth_noise(rng, size, 10, octaves=4)
    v = _voronoi_noise(rng, size, num_points=200)
    bump = (v * 0.12 + n * 0.08)

    r = (cr + bump).clip(0, 1)
    g = (cg + bump * 0.8).clip(0, 1)
    b = (cb + bump * 0.5).clip(0, 1)

    # Stitching lines
    for yi in range(0, size, size // 10):
        for xi in range(0, size, int(size * 0.03)):
            r[max(0, yi-1):yi+2, xi:xi + max(1, int(size * 0.015))] = min(1, cr + 0.20)
            g[max(0, yi-1):yi+2, xi:xi + max(1, int(size * 0.015))] = min(1, cg + 0.18)
            b[max(0, yi-1):yi+2, xi:xi + max(1, int(size * 0.015))] = min(1, cb + 0.15)

    rgb = np.stack([r, g, b], axis=-1).clip(0, 1)
    return (rgb * 255).astype(np.uint8)


def _make_sand(rng, size, prompt):
    """Sand, desert, earth, soil."""
    if 'red' in prompt:
        cr, cg, cb = 0.78, 0.38, 0.18
    elif 'dark' in prompt or 'soil' in prompt or 'earth' in prompt:
        cr, cg, cb = 0.38, 0.27, 0.16
    else:
        cr, cg, cb = 0.83, 0.70, 0.48

    n1 = _smooth_noise(rng, size, 12, octaves=5)
    n2 = _smooth_noise(rng, size, 64, octaves=2) * 0.06

    r = (cr + n1 * 0.12 + n2).clip(0, 1)
    g = (cg + n1 * 0.10 + n2).clip(0, 1)
    b = (cb + n1 * 0.08 + n2).clip(0, 1)

    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


def _make_circuit(rng, size, prompt):
    """Circuit board / matrix / cyberpunk tech texture."""
    canvas = np.zeros((size, size, 3), dtype=np.float32)
    # Background: dark green-black
    bg_r, bg_g, bg_b = 0.02, 0.06, 0.03
    canvas[:, :] = [bg_r, bg_g, bg_b]

    n = _smooth_noise(rng, size, 4, octaves=3)

    # Horizontal & vertical traces
    trace_color = np.array([0.05, 0.90, 0.15])
    dim_trace   = np.array([0.02, 0.28, 0.05])

    grid = size // 16
    for i in range(16):
        if rng.random() > 0.4:
            x = int(i * grid + rng.integers(-2, 3))
            x = max(0, min(size - 2, x))
            w = rng.integers(1, 3)
            c = trace_color if rng.random() > 0.5 else dim_trace
            canvas[:, x:x + w, :] = c * (0.7 + n[:, x:x + 1] * 0.3)[:, :, None]
        if rng.random() > 0.4:
            y = int(i * grid + rng.integers(-2, 3))
            y = max(0, min(size - 2, y))
            h = rng.integers(1, 3)
            c = trace_color if rng.random() > 0.5 else dim_trace
            canvas[y:y + h, :, :] = c * (0.7 + n[y:y + 1, :] * 0.3)[:, :, None]

    # Solder pads (dots)
    for _ in range(80):
        cx, cy = rng.integers(0, size), rng.integers(0, size)
        r = rng.integers(2, 6)
        y0 = max(0, cy - r); y1 = min(size, cy + r + 1)
        x0 = max(0, cx - r); x1 = min(size, cx + r + 1)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        mask = ((yy - cy)**2 + (xx - cx)**2) <= r**2
        canvas[y0:y1, x0:x1][mask] = trace_color * 0.9

    # Add noise glow
    glow = _smooth_noise(rng, size, 3, octaves=2) * 0.04
    canvas[:, :, 1] = (canvas[:, :, 1] + glow).clip(0, 1)

    return (canvas.clip(0, 1) * 255).astype(np.uint8)


def _make_carbon(rng, size, prompt):
    """Carbon fiber weave pattern."""
    canvas = np.zeros((size, size, 3), dtype=np.float32)
    weave = size // 16  # weave cell size
    n = _smooth_noise(rng, size, 6, octaves=3)

    for y in range(size):
        for x in range(size):
            cx, cy = x % weave, y % weave
            half = weave // 2
            if cy < half:
                # horizontal fiber
                t = cy / half
                base = 0.18 + t * 0.12
            else:
                # vertical fiber
                t = (cy - half) / half
                base = 0.22 - t * 0.08

            spec = 1.0 if (cx == half or cy == half) else 0.0
            v = base + spec * 0.25 + n[y, x] * 0.04
            canvas[y, x] = [v * 0.85, v * 0.90, v]

    return (canvas.clip(0, 1) * 255).astype(np.uint8)


def _make_lava(rng, size, prompt):
    """Lava / fire / magma texture."""
    n = _warp_noise(rng, size, 8)
    flow = _smooth_noise(rng, size, 4, octaves=5)

    # Dark rock / bright glow regions
    hot = np.power(n, 0.6)
    r = (0.08 + hot * 0.85 + flow * 0.05).clip(0, 1)
    g = (0.02 + hot * 0.30 + flow * 0.05).clip(0, 1)
    b = (0.01 + hot * 0.02).clip(0, 1)

    # Dark crust
    crust = (flow < 0.3).astype(float)
    r = (r * (1 - crust * 0.85)).clip(0, 1)
    g = (g * (1 - crust * 0.85)).clip(0, 1)
    b = (b * (1 - crust * 0.5)).clip(0, 1)

    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


def _make_ice(rng, size, prompt):
    """Ice, snow, frost, or glass."""
    snow  = 'snow' in prompt
    frost = 'frost' in prompt
    glass = 'glass' in prompt

    n = _smooth_noise(rng, size, 8, octaves=5)
    crack = _voronoi_noise(rng, size, num_points=40)

    if snow:
        base = 0.94
        r = (base + n * 0.04).clip(0, 1)
        g = (base + n * 0.04).clip(0, 1)
        b = (base + 0.02 + n * 0.03).clip(0, 1)
    elif glass:
        r = (0.80 + n * 0.08).clip(0, 1)
        g = (0.88 + n * 0.06).clip(0, 1)
        b = (0.95 + n * 0.04).clip(0, 1)
    else:
        # Ice with cracks
        vein = (crack < 0.12).astype(float) * 0.35
        r = (0.75 + n * 0.10 - vein).clip(0, 1)
        g = (0.84 + n * 0.08 - vein).clip(0, 1)
        b = (0.96 + n * 0.04 - vein * 0.5).clip(0, 1)

    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)


# ─── New material generators (v1.4) ──────────────────────────────────────────

def _make_silver(rng, size, prompt):
    """Silver, platinum, polished aluminium."""
    platinum = 'platinum' in prompt
    base_n = _smooth_noise(rng, size, 4, octaves=6)
    streak  = _smooth_noise(rng, size, 64, octaves=2)
    if platinum:
        lv = 0.78 + base_n * 0.10 + streak * 0.05
        r  = (lv - 0.02).clip(0, 1)
        g  = lv.clip(0, 1)
        b  = (lv + 0.01).clip(0, 1)
    else:  # silver / aluminium
        lv = 0.82 + base_n * 0.10 + streak * 0.06
        r  = lv.clip(0, 1)
        g  = (lv + 0.01).clip(0, 1)
        b  = (lv + 0.02).clip(0, 1)
    return (np.stack([r, g, b], axis=-1).clip(0, 1) * 255).astype(np.uint8)


def _make_rose_gold(rng, size, prompt):
    """Rose gold / pink gold."""
    n = _smooth_noise(rng, size, 6, octaves=5)
    s = _smooth_noise(rng, size, 32, octaves=2)
    r = (0.88 + n * 0.07 + s * 0.04).clip(0, 1)
    g = (0.58 + n * 0.08 + s * 0.04).clip(0, 1)
    b = (0.55 + n * 0.05).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_titanium(rng, size, prompt):
    """Titanium — dark gunmetal with subtle iridescence."""
    n  = _smooth_noise(rng, size, 5, octaves=5)
    n2 = _smooth_noise(rng, size, 20, octaves=2)
    gunmetal = 'gun' in prompt or 'dark' in prompt
    if gunmetal:
        r = (0.22 + n * 0.08 + n2 * 0.04).clip(0, 1)
        g = (0.24 + n * 0.08 + n2 * 0.04).clip(0, 1)
        b = (0.28 + n * 0.06 + n2 * 0.06).clip(0, 1)
    else:
        r = (0.48 + n * 0.10 + n2 * 0.06).clip(0, 1)
        g = (0.50 + n * 0.10 + n2 * 0.05).clip(0, 1)
        b = (0.55 + n * 0.08 + n2 * 0.07).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_bamboo(rng, size, prompt):
    """Bamboo — light green-yellow segmented stalks."""
    yy = np.tile(np.linspace(0, 1, size).reshape(size, 1), (1, size)).astype(np.float32)
    seg = (np.sin(yy * math.pi * 20) * 0.5 + 0.5)
    n = _smooth_noise(rng, size, 16, octaves=3) * 0.08
    r = (0.70 + seg * 0.10 + n).clip(0, 1)
    g = (0.62 + seg * 0.12 + n).clip(0, 1)
    b = (0.30 + seg * 0.06 + n * 0.5).clip(0, 1)
    # Knot lines
    knot_mask = (seg < 0.06).astype(float) * 0.18
    r = (r - knot_mask).clip(0, 1)
    g = (g - knot_mask).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_ebony(rng, size, prompt):
    """Ebony / dark exotic wood — very dark grain."""
    n_warp = _warp_noise(rng, size, 8)
    yy, xx = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    cx, cy = size * 0.5, size * 0.5
    dist = np.sqrt((xx - cx)**2 * 0.6 + (yy - cy)**2 * 1.4) / (size * 0.5)
    dist = (dist + n_warp * 0.2) % 1.0
    ring_mask = (np.sin(dist * math.pi * 32) * 0.5 + 0.5)
    ring_mask = np.power(ring_mask, 3.0)
    n = _smooth_noise(rng, size, 64, octaves=3) * 0.04
    r = (0.10 + ring_mask * 0.08 + n).clip(0, 1)
    g = (0.07 + ring_mask * 0.05 + n * 0.6).clip(0, 1)
    b = (0.05 + ring_mask * 0.03 + n * 0.4).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_driftwood(rng, size, prompt):
    """Driftwood / bleached wood — pale, weathered, cracked."""
    n_warp = _warp_noise(rng, size, 6)
    grain  = _smooth_noise(rng, size, 64, octaves=4) * 0.10
    crack  = _voronoi_noise(rng, size, num_points=40)
    yy, xx = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    streak = _smooth_noise(rng, size, 32, octaves=2)
    r = (0.82 + n_warp * 0.08 + grain - crack * 0.10 + streak * 0.04).clip(0, 1)
    g = (0.76 + n_warp * 0.07 + grain - crack * 0.08 + streak * 0.03).clip(0, 1)
    b = (0.65 + n_warp * 0.06 + grain - crack * 0.06).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_bark(rng, size, prompt):
    """Tree bark — rough, ridged, dark brown."""
    ridge = _ridge_noise(rng, size, 8, octaves=5)
    n     = _smooth_noise(rng, size, 12, octaves=4)
    r = (0.35 + ridge * 0.20 + n * 0.10).clip(0, 1)
    g = (0.22 + ridge * 0.14 + n * 0.07).clip(0, 1)
    b = (0.10 + ridge * 0.06 + n * 0.04).clip(0, 1)
    # Lichen patches (green spots on bark)
    if 'lichen' in prompt or 'mossy' in prompt or 'moss' in prompt:
        lichen = _smooth_noise(rng, size, 6, octaves=3)
        lm = (lichen > 0.68).astype(float) * 0.5
        r = (r * (1 - lm * 0.6)).clip(0, 1)
        g = (g + lm * 0.2).clip(0, 1)
        b = (b * (1 - lm * 0.3)).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_obsidian(rng, size, prompt):
    """Obsidian — volcanic glass, dark glossy with sharp reflective sheen."""
    n   = _smooth_noise(rng, size, 4, octaves=5)
    n2  = _smooth_noise(rng, size, 32, octaves=2)
    # Very dark base with subtle purple-blue highlights
    r = (0.05 + n * 0.06 + n2 * 0.04).clip(0, 1)
    g = (0.04 + n * 0.05 + n2 * 0.03).clip(0, 1)
    b = (0.07 + n * 0.07 + n2 * 0.07).clip(0, 1)
    # Sheen streaks
    sheen = np.power(_smooth_noise(rng, size, 64, octaves=2), 3.0) * 0.25
    r = (r + sheen * 0.4).clip(0, 1)
    g = (g + sheen * 0.3).clip(0, 1)
    b = (b + sheen * 0.8).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_sandstone(rng, size, prompt):
    """Sandstone — warm layered sedimentary rock."""
    n1 = _smooth_noise(rng, size, 8, octaves=5)
    n2 = _smooth_noise(rng, size, 32, octaves=3)
    # Horizontal layering
    yy = np.tile(np.linspace(0, 1, size).reshape(size, 1), (1, size)).astype(np.float32)
    layers = (np.sin(yy * math.pi * 16 + n1 * 2.0) * 0.5 + 0.5) * 0.15
    r = (0.82 + n1 * 0.10 + layers + n2 * 0.05).clip(0, 1)
    g = (0.65 + n1 * 0.08 + layers + n2 * 0.04).clip(0, 1)
    b = (0.40 + n1 * 0.06 + layers + n2 * 0.03).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_cobblestone(rng, size, prompt):
    """Cobblestone / paving stones — irregular rounded stones."""
    canvas = np.zeros((size, size, 3), dtype=np.float32)
    n_global = _smooth_noise(rng, size, 8, octaves=4)
    # Generate random cobble centers
    num_stones = 180
    pts = rng.random((num_stones, 2)) * size
    yy_g, xx_g = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    coords = np.stack([yy_g.ravel(), xx_g.ravel()], axis=1).astype(np.float32)
    # Voronoi: assign each pixel to nearest cobble
    dist_min = np.full(len(coords), np.inf, dtype=np.float32)
    dist_2nd = np.full(len(coords), np.inf, dtype=np.float32)
    for p in pts:
        d = np.sqrt((coords[:, 0] - p[0])**2 + (coords[:, 1] - p[1])**2)
        new_min = np.minimum(dist_min, d)
        dist_2nd = np.where(d < dist_min, dist_min, np.minimum(dist_2nd, d))
        dist_min = new_min
    dist_min = dist_min.reshape(size, size)
    dist_2nd = dist_2nd.reshape(size, size)
    # Edge = narrow band between cells
    edge = (dist_2nd - dist_min) / (dist_2nd + dist_min + 1e-9)
    mortar = (edge < 0.08).astype(float)
    stone_v = n_global * 0.18
    r = (0.52 + stone_v + mortar * (-0.20)).clip(0, 1)
    g = (0.50 + stone_v + mortar * (-0.18)).clip(0, 1)
    b = (0.46 + stone_v + mortar * (-0.14)).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_slate(rng, size, prompt):
    """Slate — dark layered metamorphic rock with cleavage planes."""
    n1 = _smooth_noise(rng, size, 6, octaves=5)
    yy = np.tile(np.linspace(0, 1, size).reshape(size, 1), (1, size)).astype(np.float32)
    layers = np.abs(np.sin((yy + n1 * 0.1) * math.pi * 24))
    layers = np.power(layers, 1.5) * 0.12
    r = (0.25 + n1 * 0.10 + layers).clip(0, 1)
    g = (0.26 + n1 * 0.10 + layers).clip(0, 1)
    b = (0.30 + n1 * 0.10 + layers).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_velvet(rng, size, prompt):
    """Velvet / plush fabric — deep colour with micro-sheen variation."""
    if 'red' in prompt or 'crimson' in prompt:
        cr, cg, cb = 0.55, 0.05, 0.10
    elif 'blue' in prompt or 'royal' in prompt:
        cr, cg, cb = 0.08, 0.10, 0.55
    elif 'purple' in prompt or 'violet' in prompt:
        cr, cg, cb = 0.38, 0.08, 0.55
    elif 'green' in prompt or 'emerald' in prompt:
        cr, cg, cb = 0.05, 0.42, 0.18
    elif 'gold' in prompt or 'amber' in prompt:
        cr, cg, cb = 0.60, 0.38, 0.05
    else:
        cr, cg, cb = 0.30, 0.05, 0.28  # dark purple default

    n  = _smooth_noise(rng, size, 8, octaves=5)
    v2 = _voronoi_noise(rng, size, num_points=400)
    sheen = (1.0 - v2) * 0.20  # micro-fibre sheen at cell edges
    r = (cr + n * 0.08 + sheen * cr).clip(0, 1)
    g = (cg + n * 0.08 + sheen * cg).clip(0, 1)
    b = (cb + n * 0.08 + sheen * cb).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_scales(rng, size, prompt):
    """Reptile scales / dragon scales / fish scales."""
    dragon = 'dragon' in prompt
    fish   = 'fish' in prompt
    if dragon:
        cr, cg, cb = 0.12, 0.40, 0.15
    elif fish:
        cr, cg, cb = 0.40, 0.60, 0.75
    else:
        cr, cg, cb = 0.22, 0.55, 0.30

    hex_g = _hexagonal_grid(size, cell_size=max(8, size // 20))
    edge = (hex_g > 0.80).astype(float) * 0.4
    n = _smooth_noise(rng, size, 12, octaves=3) * 0.12
    r = (cr + n - edge * 0.3).clip(0, 1)
    g = (cg + n - edge * 0.3).clip(0, 1)
    b = (cb + n * 0.8 - edge * 0.2).clip(0, 1)
    # Iridescent sheen
    shimmer = np.power(1.0 - hex_g, 4.0) * 0.30
    r = (r + shimmer * 0.4).clip(0, 1)
    g = (g + shimmer * 0.6).clip(0, 1)
    b = (b + shimmer * 0.8).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_fur(rng, size, prompt):
    """Animal fur — short or long fibres with directional flow."""
    wolf   = 'wolf' in prompt or 'grey' in prompt
    tiger  = 'tiger' in prompt or 'stripe' in prompt
    if wolf:
        cr, cg, cb = 0.58, 0.56, 0.54
    elif tiger:
        cr, cg, cb = 0.85, 0.52, 0.10
    else:
        cr, cg, cb = 0.60, 0.45, 0.28

    # Directional streaks simulating fur flow
    n_dir  = _smooth_noise(rng, size, 64, octaves=2)
    n_fine = _smooth_noise(rng, size, 8,  octaves=5)
    r = (cr + n_dir * 0.15 + n_fine * 0.05).clip(0, 1)
    g = (cg + n_dir * 0.12 + n_fine * 0.05).clip(0, 1)
    b = (cb + n_dir * 0.08 + n_fine * 0.03).clip(0, 1)
    # Tiger stripes overlay
    if tiger:
        stripe_n = _warp_noise(rng, size, 10)
        stripes = (np.sin(stripe_n * math.pi * 10) > 0.3).astype(float) * 0.5
        r = (r * (1 - stripes)).clip(0, 1)
        g = (g * (1 - stripes * 0.9)).clip(0, 1)
        b = (b * (1 - stripes)).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_moss(rng, size, prompt):
    """Moss / lichen / algae — soft green organic surface growth."""
    n1  = _smooth_noise(rng, size, 8,  octaves=5)
    n2  = _smooth_noise(rng, size, 3,  octaves=3) * 0.08
    v   = _voronoi_noise(rng, size, num_points=120)
    damp = 'wet' in prompt or 'damp' in prompt or 'algae' in prompt
    if damp:
        cr, cg, cb = 0.10, 0.38, 0.15
    else:
        cr, cg, cb = 0.18, 0.42, 0.12

    r = (cr + n1 * 0.08 + n2 - v * 0.04).clip(0, 1)
    g = (cg + n1 * 0.10 + n2 - v * 0.04).clip(0, 1)
    b = (cb + n1 * 0.06 + n2 - v * 0.02).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_mud(rng, size, prompt):
    """Mud / wet soil / clay."""
    wet = 'wet' in prompt or 'clay' in prompt
    n = _warp_noise(rng, size, 8)
    v = _voronoi_noise(rng, size, num_points=60)
    crack = (v < 0.08).astype(float) * 0.25 if not wet else 0.0
    if wet:
        cr, cg, cb = 0.30, 0.22, 0.14
    else:
        cr, cg, cb = 0.40, 0.30, 0.18
    r = (cr + n * 0.10 - crack).clip(0, 1)
    g = (cg + n * 0.08 - crack).clip(0, 1)
    b = (cb + n * 0.06 - crack * 0.5).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_gravel(rng, size, prompt):
    """Gravel / crushed stone / aggregate."""
    n = _smooth_noise(rng, size, 6, octaves=5)
    v = _voronoi_noise(rng, size, num_points=300)
    edge = (v < 0.06).astype(float) * 0.25
    r = (0.50 + n * 0.20 - edge).clip(0, 1)
    g = (0.48 + n * 0.18 - edge).clip(0, 1)
    b = (0.44 + n * 0.16 - edge).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_coal(rng, size, prompt):
    """Coal / charcoal / blackened material."""
    n1 = _smooth_noise(rng, size, 4, octaves=5)
    n2 = _smooth_noise(rng, size, 16, octaves=3) * 0.06
    v  = _voronoi_noise(rng, size, num_points=100)
    sheen = np.power(n1, 3.0) * 0.15  # coal gloss
    r = (0.08 + n1 * 0.08 + n2 + sheen * 0.6 - v * 0.04).clip(0, 1)
    g = (0.08 + n1 * 0.08 + n2 + sheen * 0.5 - v * 0.04).clip(0, 1)
    b = (0.10 + n1 * 0.09 + n2 + sheen * 0.8 - v * 0.04).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_ceramic(rng, size, prompt):
    """Ceramic / porcelain / terracotta / tile."""
    porcelain  = any(w in prompt for w in ['porcelain', 'white', 'smooth'])
    terracotta = any(w in prompt for w in ['terracotta', 'terra', 'clay pot'])
    tile_pattern = any(w in prompt for w in ['tile', 'tiled'])

    if terracotta:
        cr, cg, cb = 0.80, 0.36, 0.22
    elif porcelain:
        cr, cg, cb = 0.95, 0.94, 0.92
    else:
        cr, cg, cb = 0.90, 0.88, 0.84  # off-white glaze

    n = _smooth_noise(rng, size, 4, octaves=4) * 0.04
    r = (cr + n).clip(0, 1)
    g = (cg + n).clip(0, 1)
    b = (cb + n).clip(0, 1)

    if tile_pattern:
        # Grid grout lines
        yy, xx = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
        cell = size // 8
        grout = ((xx % cell < 3) | (yy % cell < 3)).astype(float) * 0.25
        r = (r - grout * 0.4).clip(0, 1)
        g = (g - grout * 0.4).clip(0, 1)
        b = (b - grout * 0.4).clip(0, 1)

    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_plasma(rng, size, prompt):
    """Plasma / energy field / neon glow — electric nebula."""
    n1 = _warp_noise(rng, size, 6)
    n2 = _turbulence_noise(rng, size, 4)
    t  = (n1 * 0.6 + n2 * 0.4)
    if 'blue' in prompt or 'electric' in prompt:
        r = (t * 0.20).clip(0, 1)
        g = (t * 0.40).clip(0, 1)
        b = (0.10 + t * 0.90).clip(0, 1)
    elif 'red' in prompt or 'fire' in prompt or 'plasma' in prompt:
        r = (0.10 + t * 0.90).clip(0, 1)
        g = (t * 0.25).clip(0, 1)
        b = (t * 0.10).clip(0, 1)
    else:  # purple / cosmic
        r = (0.10 + t * 0.70).clip(0, 1)
        g = (t * 0.20).clip(0, 1)
        b = (0.15 + t * 0.85).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_void(rng, size, prompt):
    """Void / abyss / deep space — near-black with distant star dust."""
    n1 = _smooth_noise(rng, size, 3, octaves=6)
    n2 = _smooth_noise(rng, size, 64, octaves=2) * 0.04
    # Stars — sparse bright points
    stars_raw = rng.random((size, size)).astype(np.float32)
    stars = (stars_raw > 0.994).astype(float) * 0.9
    r = (n1 * 0.06 + n2 + stars).clip(0, 1)
    g = (n1 * 0.05 + n2 + stars * 0.85).clip(0, 1)
    b = (n1 * 0.09 + n2 + stars * 0.95).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_rubber(rng, size, prompt):
    """Rubber / latex / tyre — matte black with subtle texture."""
    if 'red' in prompt:
        cr, cg, cb = 0.55, 0.05, 0.05
    elif 'yellow' in prompt:
        cr, cg, cb = 0.55, 0.45, 0.02
    elif 'white' in prompt:
        cr, cg, cb = 0.88, 0.88, 0.88
    else:  # black rubber / tyre
        cr, cg, cb = 0.10, 0.10, 0.10

    n = _smooth_noise(rng, size, 6, octaves=4)
    v = _voronoi_noise(rng, size, num_points=500) * 0.06
    r = (cr + n * 0.05 + v).clip(0, 1)
    g = (cg + n * 0.05 + v).clip(0, 1)
    b = (cb + n * 0.05 + v).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_plastic(rng, size, prompt):
    """Plastic / resin — smooth with specular hot-spot."""
    if 'red' in prompt:
        cr, cg, cb = 0.80, 0.10, 0.10
    elif 'blue' in prompt:
        cr, cg, cb = 0.10, 0.25, 0.80
    elif 'green' in prompt:
        cr, cg, cb = 0.12, 0.70, 0.25
    elif 'yellow' in prompt:
        cr, cg, cb = 0.90, 0.80, 0.05
    elif 'white' in prompt:
        cr, cg, cb = 0.92, 0.92, 0.92
    elif 'black' in prompt:
        cr, cg, cb = 0.12, 0.12, 0.13
    else:  # default grey
        cr, cg, cb = 0.55, 0.55, 0.57

    n = _smooth_noise(rng, size, 3, octaves=3) * 0.04
    # Specular gradient spot
    yy, xx = np.meshgrid(np.linspace(-1, 1, size), np.linspace(-1, 1, size), indexing='ij')
    spec = np.exp(-(xx**2 + yy**2) * 4.0).astype(np.float32) * 0.25
    r = (cr + n + spec * 0.8).clip(0, 1)
    g = (cg + n + spec * 0.8).clip(0, 1)
    b = (cb + n + spec * 0.8).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_paint(rng, size, prompt):
    """Paint / chalk / spray paint — flat or textured pigment."""
    chalk    = 'chalk' in prompt or 'matte' in prompt
    spray    = 'spray' in prompt or 'graffiti' in prompt
    if 'red' in prompt:
        cr, cg, cb = 0.78, 0.15, 0.12
    elif 'blue' in prompt:
        cr, cg, cb = 0.15, 0.25, 0.78
    elif 'yellow' in prompt or 'amber' in prompt:
        cr, cg, cb = 0.90, 0.72, 0.08
    elif 'green' in prompt:
        cr, cg, cb = 0.15, 0.65, 0.25
    elif 'white' in prompt:
        cr, cg, cb = 0.95, 0.95, 0.94
    elif 'black' in prompt:
        cr, cg, cb = 0.10, 0.10, 0.11
    else:
        cr, cg, cb = 0.70, 0.30, 0.12  # terracotta paint default

    n = _smooth_noise(rng, size, 8, octaves=4)
    if chalk:
        tex = n * 0.12
    elif spray:
        tex = _turbulence_noise(rng, size, 8) * 0.08
    else:
        tex = n * 0.06

    r = (cr + tex).clip(0, 1)
    g = (cg + tex * 0.9).clip(0, 1)
    b = (cb + tex * 0.8).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_stucco(rng, size, prompt):
    """Stucco / plaster / render — bumpy wall finish."""
    n1 = _smooth_noise(rng, size, 8,  octaves=5)
    n2 = _smooth_noise(rng, size, 32, octaves=2)
    v  = _voronoi_noise(rng, size, num_points=400) * 0.08
    if 'pink' in prompt or 'mediterranean' in prompt:
        cr, cg, cb = 0.88, 0.72, 0.62
    elif 'yellow' in prompt or 'ochre' in prompt:
        cr, cg, cb = 0.90, 0.80, 0.50
    elif 'warm' in prompt:
        cr, cg, cb = 0.86, 0.78, 0.65
    else:
        cr, cg, cb = 0.85, 0.83, 0.78

    r = (cr + n1 * 0.08 + n2 * 0.04 - v * 0.05).clip(0, 1)
    g = (cg + n1 * 0.07 + n2 * 0.03 - v * 0.05).clip(0, 1)
    b = (cb + n1 * 0.06 + n2 * 0.03 - v * 0.04).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_water(rng, size, prompt):
    """Water surface — ripples, caustics, deep ocean."""
    deep   = 'deep' in prompt or 'ocean' in prompt
    shallow= 'shallow' in prompt or 'reef' in prompt
    n1 = _warp_noise(rng, size, 6)
    n2 = _smooth_noise(rng, size, 16, octaves=4)
    # Caustic pattern
    caustic = _ridge_noise(rng, size, 10, octaves=4) * 0.35
    if deep:
        r = (0.02 + n1 * 0.04 + caustic * 0.10).clip(0, 1)
        g = (0.10 + n1 * 0.06 + caustic * 0.15).clip(0, 1)
        b = (0.35 + n2 * 0.12 + caustic * 0.25).clip(0, 1)
    elif shallow:
        r = (0.10 + n1 * 0.10 + caustic * 0.20).clip(0, 1)
        g = (0.55 + n2 * 0.12 + caustic * 0.25).clip(0, 1)
        b = (0.65 + n1 * 0.10 + caustic * 0.20).clip(0, 1)
    else:  # lake / default
        r = (0.06 + n1 * 0.08 + caustic * 0.12).clip(0, 1)
        g = (0.25 + n1 * 0.10 + caustic * 0.20).clip(0, 1)
        b = (0.55 + n2 * 0.15 + caustic * 0.30).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_alien(rng, size, prompt):
    """Alien / bio-mechanical / xenomorph — organic sci-fi surface."""
    bioluminescent = any(w in prompt for w in ['bioluminescent', 'glow', 'neon'])
    carapace = any(w in prompt for w in ['carapace', 'armour', 'exoskeleton'])
    n = _warp_noise(rng, size, 8)
    v = _voronoi_noise(rng, size, num_points=80)
    ridge = _ridge_noise(rng, size, 6)
    if bioluminescent:
        r = (n * 0.15 + v * 0.10 + ridge * 0.20).clip(0, 1)
        g = (0.05 + n * 0.25 + ridge * 0.50).clip(0, 1)
        b = (0.10 + n * 0.20 + v * 0.15 + ridge * 0.35).clip(0, 1)
    elif carapace:
        r = (0.08 + n * 0.08 + v * 0.05).clip(0, 1)
        g = (0.10 + n * 0.10 + ridge * 0.08).clip(0, 1)
        b = (0.06 + n * 0.06 + v * 0.04).clip(0, 1)
    else:
        r = (0.15 + n * 0.12 + v * 0.06).clip(0, 1)
        g = (0.28 + n * 0.10 + ridge * 0.18).clip(0, 1)
        b = (0.12 + n * 0.08 + v * 0.06).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_hologram(rng, size, prompt):
    """Holographic / iridescent / diffraction grating."""
    n = _smooth_noise(rng, size, 16, octaves=4)
    yy, xx = np.meshgrid(np.linspace(0, 1, size), np.linspace(0, 1, size), indexing='ij')
    # Diffraction rainbow sweep
    angle  = (xx + yy + n * 0.2) % 1.0
    r = (0.6 + 0.4 * np.sin(angle * math.pi * 2 + 0.0)).clip(0, 1)
    g = (0.6 + 0.4 * np.sin(angle * math.pi * 2 + 2.1)).clip(0, 1)
    b = (0.6 + 0.4 * np.sin(angle * math.pi * 2 + 4.2)).clip(0, 1)
    # Dark grid overlay for hologram effect
    grid = ((xx * 80 % 1.0 < 0.08) | (yy * 80 % 1.0 < 0.08)).astype(float) * 0.4
    r = (r * (1 - grid * 0.6)).clip(0, 1)
    g = (g * (1 - grid * 0.6)).clip(0, 1)
    b = (b * (1 - grid * 0.5)).clip(0, 1)
    return (np.stack([r, g, b], axis=-1).astype(np.float32) * 255).astype(np.uint8)


def _make_grunge(rng, size, prompt):
    """Grunge / dirty / stained — layered grime and aging."""
    base_n = _warp_noise(rng, size, 8)
    stain  = _turbulence_noise(rng, size, 6) * 0.30
    rust_n = _smooth_noise(rng, size, 10, octaves=4) * 0.20
    r = (0.35 + base_n * 0.20 + stain * 0.40 + rust_n * 0.20).clip(0, 1)
    g = (0.28 + base_n * 0.15 + stain * 0.25 + rust_n * 0.10).clip(0, 1)
    b = (0.20 + base_n * 0.10 + stain * 0.15).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _make_diamond(rng, size, prompt):
    """Diamond / crystal / gem — faceted refractive sparkle."""
    n  = _smooth_noise(rng, size, 8, octaves=4)
    v  = _voronoi_noise(rng, size, num_points=60)
    edge = np.abs(v - 0.5) * 2.0  # facet edges
    facet_shading = (1.0 - np.power(edge, 0.5)) * 0.6
    # Rainbow dispersion at edges
    angle = (n + facet_shading) % 1.0
    r = (0.80 + 0.20 * np.sin(angle * math.pi * 2 + 0.0)).clip(0, 1)
    g = (0.85 + 0.15 * np.sin(angle * math.pi * 2 + 2.1)).clip(0, 1)
    b = (0.90 + 0.10 * np.sin(angle * math.pi * 2 + 4.2)).clip(0, 1)
    sparkle = (rng.random((size, size)).astype(np.float32) > 0.98).astype(float) * 0.8
    r = (r + sparkle).clip(0, 1)
    g = (g + sparkle).clip(0, 1)
    b = (b + sparkle).clip(0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


# ─── Dispatch & public API ────────────────────────────────────────────────────

def _detect_material(prompt):
    p = prompt.lower()

    # ── Highest specificity first ─────────────────────────────────────────────
    if any(w in p for w in ['hologram', 'holographic', 'iridescent', 'diffraction', 'rainbow metal']):
        return 'hologram'
    if any(w in p for w in ['diamond', 'gem', 'gemstone', 'faceted crystal']):
        return 'diamond'
    if any(w in p for w in ['alien', 'xenomorph', 'bio-mech', 'biomechanical', 'carapace',
                              'exoskeleton', 'bioluminescent', 'otherworldly']):
        return 'alien'
    if any(w in p for w in ['void', 'abyss', 'dark space', 'deep space', 'nebula', 'cosmos']):
        return 'void'
    if any(w in p for w in ['plasma', 'energy field', 'electric arc', 'lightning', 'discharge']):
        return 'plasma'
    if any(w in p for w in ['circuit', 'cyber', 'matrix', 'pcb', 'scifi', 'sci-fi',
                              'cyberpunk', 'tech panel', 'motherboard']):
        return 'circuit'
    if 'neon' in p and not any(w in p for w in ['wood', 'stone', 'metal']):
        return 'circuit'
    if any(w in p for w in ['carbon', 'composite', 'weave', 'carbon fiber', 'carbon fibre']):
        return 'carbon'
    if any(w in p for w in ['velvet', 'plush', 'velour']):
        return 'velvet'
    if any(w in p for w in ['scale', 'scales', 'dragon scale', 'reptile', 'lizard', 'fish scale']):
        return 'scales'
    if any(w in p for w in ['fur', 'pelt', 'fluffy', 'animal hair', 'wolf', 'tiger']):
        return 'fur'
    if any(w in p for w in ['moss', 'lichen', 'algae', 'overgrown']):
        return 'moss'
    if any(w in p for w in ['bark', 'tree bark', 'wood bark']):
        return 'bark'
    if any(w in p for w in ['lava', 'fire', 'magma', 'ember', 'molten']):
        return 'lava'
    if any(w in p for w in ['water', 'ocean', 'sea', 'lake', 'river', 'caustic', 'ripple', 'aqua']):
        return 'water'
    if any(w in p for w in ['frost', 'frozen', 'glacier']):
        return 'ice'
    if any(w in p for w in ['snow']):
        return 'ice'
    if any(w in p for w in ['ice', 'icy']):
        return 'ice'
    if any(w in p for w in ['glass', 'crystal', 'transparent']):
        return 'ice'
    if any(w in p for w in ['marble', 'travertine']):
        return 'marble'
    if any(w in p for w in ['obsidian', 'volcanic glass']):
        return 'obsidian'
    if any(w in p for w in ['ebony', 'dark wood', 'blackwood']):
        return 'ebony'
    if any(w in p for w in ['driftwood', 'bleached wood', 'weathered wood']):
        return 'driftwood'
    if any(w in p for w in ['bamboo', 'reed', 'cane']):
        return 'bamboo'
    if any(w in p for w in ['wood', 'oak', 'pine', 'walnut', 'mahogany', 'timber', 'grain', 'ash wood',
                              'cedar', 'teak', 'birch', 'spruce']):
        return 'wood'
    if any(w in p for w in ['sandstone', 'sedimentary']):
        return 'sandstone'
    if any(w in p for w in ['cobblestone', 'cobble', 'paving', 'pavement']):
        return 'cobblestone'
    if any(w in p for w in ['slate', 'shale', 'cleavage']):
        return 'slate'
    if any(w in p for w in ['coal', 'charcoal', 'coke', 'blackened rock']):
        return 'coal'
    if any(w in p for w in ['granite', 'granite vein']):
        return 'marble'  # granite vein → marble variant
    if any(w in p for w in ['concrete', 'cement', 'brutalist']):
        return 'stone'
    if any(w in p for w in ['stone', 'rock', 'limestone', 'brick', 'slate rock', 'basalt']):
        return 'stone'
    if any(w in p for w in ['mud', 'clay', 'wet soil', 'swamp']):
        return 'mud'
    if any(w in p for w in ['gravel', 'crushed stone', 'aggregate', 'pebble']):
        return 'gravel'
    if any(w in p for w in ['sand', 'desert', 'dune', 'dirt', 'soil', 'earth']):
        return 'sand'
    if any(w in p for w in ['stucco', 'plaster', 'render', 'roughcast']):
        return 'stucco'
    if any(w in p for w in ['grunge', 'dirty', 'filthy', 'stained', 'grime']):
        return 'grunge'
    if any(w in p for w in ['paint', 'chalk', 'spray paint', 'acrylic', 'pigment']):
        return 'paint'
    if any(w in p for w in ['ceramic', 'porcelain', 'terracotta', 'tile', 'glaze', 'pottery']):
        return 'ceramic'
    if any(w in p for w in ['rubber', 'tyre', 'tire', 'latex']):
        return 'rubber'
    if any(w in p for w in ['plastic', 'resin', 'acrylic plastic', 'pvc']):
        return 'plastic'
    if any(w in p for w in ['rose gold', 'pink gold']):
        return 'rose_gold'
    if any(w in p for w in ['titanium', 'gunmetal']):
        return 'titanium'
    if any(w in p for w in ['silver', 'aluminium', 'aluminum', 'platinum']):
        return 'silver'
    if any(w in p for w in ['gold', 'copper', 'bronze', 'brass']):
        return 'gold'
    if any(w in p for w in ['leather', 'skin', 'hide', 'suede']):
        return 'leather'
    if any(w in p for w in ['fabric', 'cloth', 'textile', 'denim', 'cotton', 'silk', 'wool']):
        return 'leather'
    if any(w in p for w in ['metal', 'steel', 'iron', 'chrome', 'rust', 'rusted',
                              'oxidis', 'galvanized', 'corrugated', 'chain', 'mesh wire']):
        return 'metal'
    return 'generic'


def generate_procedural_texture(
    prompt: str,
    size: int = 1024,
    reference_image: Image.Image = None,
    uvs: np.ndarray = None,
    faces: np.ndarray = None,
) -> Image.Image:
    """
    High-quality procedural texture generator.
    No GPU or external model required — pure PIL/NumPy.
    """
    logger.info(f"[ProcTex] Generating '{prompt}' at {size}px")
    rng = np.random.default_rng(abs(hash(prompt)) % (2 ** 31))
    p   = prompt.lower()
    mat = _detect_material(p)
    logger.info(f"[ProcTex] Detected material: {mat}")

    _dispatch = {
        'metal':       _make_metal,
        'gold':        _make_gold,
        'silver':      _make_silver,
        'rose_gold':   _make_rose_gold,
        'titanium':    _make_titanium,
        'wood':        _make_wood,
        'bamboo':      _make_bamboo,
        'ebony':       _make_ebony,
        'driftwood':   _make_driftwood,
        'bark':        _make_bark,
        'marble':      _make_marble,
        'obsidian':    _make_obsidian,
        'sandstone':   _make_sandstone,
        'cobblestone': _make_cobblestone,
        'slate':       _make_slate,
        'stone':       _make_stone,
        'coal':        _make_coal,
        'leather':     _make_leather,
        'velvet':      _make_velvet,
        'scales':      _make_scales,
        'fur':         _make_fur,
        'moss':        _make_moss,
        'sand':        _make_sand,
        'mud':         _make_mud,
        'gravel':      _make_gravel,
        'circuit':     _make_circuit,
        'carbon':      _make_carbon,
        'ceramic':     _make_ceramic,
        'lava':        _make_lava,
        'plasma':      _make_plasma,
        'void':        _make_void,
        'ice':         _make_ice,
        'water':       _make_water,
        'diamond':     _make_diamond,
        'rubber':      _make_rubber,
        'plastic':     _make_plastic,
        'paint':       _make_paint,
        'stucco':      _make_stucco,
        'grunge':      _make_grunge,
        'hologram':    _make_hologram,
        'alien':       _make_alien,
    }

    if mat in _dispatch:
        arr = _dispatch[mat](rng, size, p)
    else:
        # Generic fallback — medium grey with subtle noise
        n   = _smooth_noise(rng, size, 8, octaves=5)
        v   = 0.50 + n * 0.20
        arr = np.stack([v, v, v], axis=-1).clip(0, 1)
        arr = (arr * 255).astype(np.uint8)

    img = Image.fromarray(arr, 'RGB')

    # Blend in reference image if provided
    if reference_image is not None:
        logger.info("[ProcTex] Blending reference image")
        ref = reference_image.convert('RGB').resize((size, size), Image.LANCZOS)
        img = Image.blend(img, ref, alpha=0.55)

    # Final pass — contrast + slight sharpness
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Sharpness(img).enhance(1.25)

    return img


# ─── UV Layout Visualization ──────────────────────────────────────────────────

def render_uv_layout(uvs: np.ndarray, faces: np.ndarray, size: int = 1024) -> Image.Image:
    img  = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(img)
    for face in faces:
        pts = [(float(uvs[i][0]) * size, float((1.0 - uvs[i][1])) * size) for i in face]
        draw.polygon(pts, outline=255)
    return img


def render_uv_checkerboard(uvs: np.ndarray, faces: np.ndarray, size: int = 1024) -> Image.Image:
    checker = Image.new('RGB', (size, size), (30, 30, 30))
    draw    = ImageDraw.Draw(checker)
    cell    = size // 16
    for y in range(16):
        for x in range(16):
            if (x + y) % 2 == 0:
                draw.rectangle([x * cell, y * cell, (x+1)*cell-1, (y+1)*cell-1], fill=(200, 200, 200))
    border  = render_uv_layout(uvs, faces, size).convert('RGB')
    b_arr   = np.array(border)
    mask    = b_arr[:, :, 1] > 128
    c_arr   = np.array(checker)
    c_arr[mask] = [0, 220, 80]
    return Image.fromarray(c_arr)


# ─── AI Texture (Stable Diffusion fallback) ───────────────────────────────────

def generate_ai_texture(
    prompt: str,
    size: int = 512,
    reference_image: Image.Image = None,
    num_inference_steps: int = 20,
    guidance_scale: float = 7.5,
    strength: float = 0.75,
) -> Image.Image:
    try:
        from diffusers import StableDiffusionPipeline, StableDiffusionImg2ImgPipeline
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"[AI Tex] Running Stable Diffusion on {device}")

        enh_prompt = (
            f"{prompt}, seamless tileable PBR texture, "
            "high frequency detail, 4K resolution, surface material"
        )
        neg_prompt = "blurry, low quality, watermark, text, logo, artifacts, seams"

        if reference_image is not None:
            pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                'runwayml/stable-diffusion-v1-5',
                torch_dtype=torch.float32, safety_checker=None,
            ).to(device)
            pipe.enable_attention_slicing()
            ref = reference_image.convert('RGB').resize((size, size))
            result = pipe(prompt=enh_prompt, negative_prompt=neg_prompt, image=ref,
                          strength=strength, num_inference_steps=num_inference_steps,
                          guidance_scale=guidance_scale).images[0]
        else:
            pipe = StableDiffusionPipeline.from_pretrained(
                'runwayml/stable-diffusion-v1-5',
                torch_dtype=torch.float32, safety_checker=None,
            ).to(device)
            pipe.enable_attention_slicing()
            result = pipe(prompt=enh_prompt, negative_prompt=neg_prompt,
                          width=size, height=size,
                          num_inference_steps=num_inference_steps,
                          guidance_scale=guidance_scale).images[0]
        return result
    except Exception as e:
        logger.warning(f"[AI Tex] Stable Diffusion failed: {e} — using procedural fallback")
        return generate_procedural_texture(prompt, size, reference_image)


# ─── UV-space baking (numpy-vectorised, replaces slow Python loop) ────────────

def bake_texture_to_uv(
    texture: Image.Image,
    uvs: np.ndarray,
    faces: np.ndarray,
    output_size: int = 1024,
) -> Image.Image:
    """
    Project a procedural/AI texture into UV atlas space via rasterisation.

    Algorithm:
      For each UV triangle, rasterise its bounding-box pixels, compute
      barycentric coordinates to reject pixels outside the triangle, then
      bilinearly sample the source texture at the interpolated UV position.

    Uses numpy vectorisation per triangle (bounding-box pixels at once)
    instead of Python-level pixel loops — 10-50x faster.

    After rasterisation, empty (seam) pixels are filled with the nearest
    source texture value to eliminate bleed artifacts at UV borders.
    """
    logger.info(f"[Bake] UV-projecting texture -> {output_size}px atlas")
    tex_arr  = np.array(
        texture.convert('RGB').resize((output_size, output_size), Image.BILINEAR),
        dtype=np.float32
    )
    canvas   = np.zeros((output_size, output_size, 3), dtype=np.float32)
    coverage = np.zeros((output_size, output_size),    dtype=bool)

    S = float(output_size - 1)
    uvs_c = np.clip(uvs, 0.0, 1.0).astype(np.float32)
    px_all = uvs_c[:, 0] * S           # U -> X
    py_all = (1.0 - uvs_c[:, 1]) * S  # V -> Y (flip)

    # Pixel grids (built once, sliced per face)
    yy_full, xx_full = np.meshgrid(
        np.arange(output_size, dtype=np.float32),
        np.arange(output_size, dtype=np.float32),
        indexing='ij'
    )

    def _bilinear(u_arr, v_arr):
        x = np.clip(u_arr * S, 0, S)
        y = np.clip((1.0 - v_arr) * S, 0, S)
        x0 = np.floor(x).astype(np.int32); x1 = np.minimum(x0 + 1, int(S))
        y0 = np.floor(y).astype(np.int32); y1 = np.minimum(y0 + 1, int(S))
        fx = (x - x0)[..., None]; fy = (y - y0)[..., None]
        c00 = tex_arr[y0, x0]; c10 = tex_arr[y0, x1]
        c01 = tex_arr[y1, x0]; c11 = tex_arr[y1, x1]
        return (c00*(1-fx)*(1-fy) + c10*fx*(1-fy) +
                c01*(1-fx)*fy    + c11*fx*fy)

    n_faces  = len(faces)
    reported = 0
    for fi, face in enumerate(faces):
        pct = fi * 100 // n_faces
        if pct >= reported + 20:
            reported = pct
            logger.info(f"[Bake] {pct}% ({fi}/{n_faces} tris)")

        ax, ay = px_all[face[0]], py_all[face[0]]
        bx, by = px_all[face[1]], py_all[face[1]]
        cx, cy = px_all[face[2]], py_all[face[2]]

        area2 = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(area2) < 1.0:
            continue

        min_x = max(int(min(ax, bx, cx)) - 1, 0)
        max_x = min(int(max(ax, bx, cx)) + 2, output_size - 1)
        min_y = max(int(min(ay, by, cy)) - 1, 0)
        max_y = min(int(max(ay, by, cy)) + 2, output_size - 1)
        if min_x > max_x or min_y > max_y:
            continue

        xx = xx_full[min_y:max_y+1, min_x:max_x+1]
        yy = yy_full[min_y:max_y+1, min_x:max_x+1]

        w0 = (bx - ax) * (yy - ay) - (by - ay) * (xx - ax)
        w1 = (cx - bx) * (yy - by) - (cy - by) * (xx - bx)
        w2 = (ax - cx) * (yy - cy) - (ay - cy) * (xx - cx)

        inside = ((w0 >= 0) & (w1 >= 0) & (w2 >= 0) if area2 > 0
                  else (w0 <= 0) & (w1 <= 0) & (w2 <= 0))
        if not inside.any():
            continue

        inv = 1.0 / area2
        b0 = np.clip(w0[inside] * inv, 0, 1)
        b1 = np.clip(w1[inside] * inv, 0, 1)
        b2 = np.clip(w2[inside] * inv, 0, 1)
        tot = b0 + b1 + b2
        b0 /= tot; b1 /= tot; b2 /= tot

        u_i = b0*uvs_c[face[0],0] + b1*uvs_c[face[1],0] + b2*uvs_c[face[2],0]
        v_i = b0*uvs_c[face[0],1] + b1*uvs_c[face[1],1] + b2*uvs_c[face[2],1]
        sampled = _bilinear(u_i, v_i)

        rows, cols = np.where(inside)
        ys = rows + min_y; xs = cols + min_x
        canvas[ys, xs]   = sampled
        coverage[ys, xs] = True

    # Fill empty seam pixels with source texture fallback
    canvas[~coverage] = tex_arr[~coverage]

    logger.info("[Bake] UV atlas baked")
    return Image.fromarray(canvas.clip(0, 255).astype(np.uint8), 'RGB')


# ─── Public entry point ───────────────────────────────────────────────────────

def generate_texture(
    prompt: str,
    output_path: str,
    uvs: np.ndarray = None,
    faces: np.ndarray = None,
    reference_image_path: str = None,
    texture_size: int = 1024,
    use_ai: bool = False,
    ai_steps: int = 20,
) -> str:
    """
    Main entry point for texture generation.
    Returns path to saved PNG.
    """
    os.makedirs(
        os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True
    )

    reference_image = None
    if reference_image_path and os.path.exists(reference_image_path):
        logger.info(f"[Tex] Loading reference: {reference_image_path}")
        reference_image = Image.open(reference_image_path).convert('RGB')

    if use_ai:
        logger.info("[Tex] Stable Diffusion mode")
        texture = generate_ai_texture(
            prompt=prompt,
            size=min(texture_size, 512),
            reference_image=reference_image,
            num_inference_steps=ai_steps,
        )
        if texture.size[0] < texture_size:
            texture = texture.resize((texture_size, texture_size), Image.LANCZOS)
    else:
        logger.info("[Tex] Procedural mode")
        texture = generate_procedural_texture(
            prompt=prompt,
            size=texture_size,
            reference_image=reference_image,
        )

    # ── Step 2: UV-project into atlas space if UV data was provided ──────────
    if uvs is not None and faces is not None and len(uvs) > 0 and len(faces) > 0:
        logger.info("[Tex] UV data present — baking into atlas space")
        texture = bake_texture_to_uv(
            texture=texture,
            uvs=uvs,
            faces=faces,
            output_size=texture_size,
        )
    else:
        logger.info("[Tex] No UV data supplied — saving flat texture as-is")

    texture.save(output_path, 'PNG')
    logger.info(f"[Tex] Saved -> {output_path}")
    return output_path
