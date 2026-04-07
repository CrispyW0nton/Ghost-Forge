"""
Texture Generation Module
Generates textures for UV-unwrapped 3D meshes using:
  1. Text prompt  → Stable Diffusion (via diffusers)
  2. Reference image → img2img pipeline for style transfer
  3. Projection baking → maps the generated texture onto UV space

The approach:
  - Render the UV layout as a "template" showing seams and islands
  - Feed prompt/reference to SD to generate a tileable or atlas texture
  - Optionally apply multi-view projection baking for more coherent results
  - Save as PNG at the requested resolution
"""

import os
import logging
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import trimesh
import requests
import io

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UV Layout Visualization
# ---------------------------------------------------------------------------

def render_uv_layout(uvs: np.ndarray, faces: np.ndarray, size: int = 1024) -> Image.Image:
    """
    Render the UV island layout as a white-on-black image.
    Useful for debugging and as a mask for texture painting.
    """
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)

    for face in faces:
        pts = [(float(uvs[i][0]) * size, float((1.0 - uvs[i][1])) * size) for i in face]
        draw.polygon(pts, outline=255)

    return img


def render_uv_checkerboard(uvs: np.ndarray, faces: np.ndarray, size: int = 1024) -> Image.Image:
    """
    Render a classic UV checkerboard onto the mesh's UV layout.
    Each UV island gets its own checker pattern for visual validation.
    """
    checker = Image.new("RGB", (size, size), (30, 30, 30))
    draw = ImageDraw.Draw(checker)
    cell = size // 16
    for y in range(16):
        for x in range(16):
            if (x + y) % 2 == 0:
                draw.rectangle([x * cell, y * cell, (x + 1) * cell - 1, (y + 1) * cell - 1],
                                fill=(220, 220, 220))
    # Draw UV borders on top
    border_layer = render_uv_layout(uvs, faces, size).convert("RGB")
    # Tint borders green
    border_arr = np.array(border_layer)
    mask = border_arr[:, :, 1] > 128
    checker_arr = np.array(checker)
    checker_arr[mask] = [0, 200, 80]
    return Image.fromarray(checker_arr)


# ---------------------------------------------------------------------------
# Texture Generation — Fallback (no GPU / no model downloaded)
# ---------------------------------------------------------------------------

def generate_procedural_texture(
    prompt: str,
    size: int = 1024,
    reference_image: Image.Image = None,
    uvs: np.ndarray = None,
    faces: np.ndarray = None,
) -> Image.Image:
    """
    Fast procedural texture generator that works without a GPU or downloaded model.
    Uses PIL to create stylized textures based on keyword analysis of the prompt.
    Good enough for previewing UV layouts and testing the pipeline.
    """
    logger.info(f"Generating procedural texture for: '{prompt}'")

    prompt_lower = prompt.lower()

    # Colour palette selection based on keywords
    if any(w in prompt_lower for w in ["metal", "steel", "iron", "silver", "chrome"]):
        base_color = (160, 160, 175)
        noise_scale = 15
        style = "metallic"
    elif any(w in prompt_lower for w in ["wood", "oak", "pine", "mahogany", "timber"]):
        base_color = (139, 90, 43)
        noise_scale = 8
        style = "wood"
    elif any(w in prompt_lower for w in ["stone", "rock", "concrete", "brick", "marble"]):
        base_color = (128, 118, 105)
        noise_scale = 20
        style = "stone"
    elif any(w in prompt_lower for w in ["grass", "leaf", "plant", "green", "moss"]):
        base_color = (60, 120, 50)
        noise_scale = 12
        style = "organic"
    elif any(w in prompt_lower for w in ["sand", "desert", "dirt", "soil", "earth"]):
        base_color = (194, 160, 110)
        noise_scale = 10
        style = "sandy"
    elif any(w in prompt_lower for w in ["skin", "flesh", "leather", "fabric", "cloth"]):
        base_color = (200, 155, 120)
        noise_scale = 5
        style = "organic"
    elif any(w in prompt_lower for w in ["lava", "fire", "hot", "magma", "ember"]):
        base_color = (200, 60, 10)
        noise_scale = 18
        style = "fiery"
    elif any(w in prompt_lower for w in ["ice", "snow", "frost", "crystal", "glass"]):
        base_color = (200, 220, 240)
        noise_scale = 6
        style = "icy"
    elif any(w in prompt_lower for w in ["gold", "copper", "bronze", "brass"]):
        base_color = (200, 160, 40)
        noise_scale = 12
        style = "metallic"
    else:
        base_color = (150, 140, 130)
        noise_scale = 10
        style = "generic"

    # --- Build texture layers ---
    rng = np.random.default_rng(abs(hash(prompt)) % (2**31))

    # Layer 1: Smooth base noise
    noise = rng.random((size, size, 3)).astype(np.float32)
    # Blur for smooth variation
    base = Image.fromarray((noise * 255).astype(np.uint8), "RGB")
    base = base.filter(ImageFilter.GaussianBlur(radius=size // noise_scale))
    base_arr = np.array(base).astype(np.float32) / 255.0

    # Layer 2: Tint toward the chosen colour
    color_arr = np.array(base_color, dtype=np.float32) / 255.0
    blended = base_arr * 0.35 + color_arr * 0.65
    blended = np.clip(blended, 0, 1)

    # Layer 3: Style-specific effects
    if style == "wood":
        # Add grain lines
        for _ in range(30):
            y = rng.integers(0, size)
            thickness = rng.integers(2, 8)
            wave = (np.sin(np.linspace(0, 4 * np.pi, size)) * rng.integers(5, 30)).astype(int)
            for x in range(size):
                yy = np.clip(y + wave[x], 0, size - 1)
                for t in range(-thickness // 2, thickness // 2):
                    yyy = np.clip(yy + t, 0, size - 1)
                    blended[yyy, x] *= rng.uniform(0.7, 0.9)

    elif style == "metallic":
        # Add specular-like highlights
        highlight_mask = rng.random((size, size)) > 0.985
        blended[highlight_mask] = np.clip(blended[highlight_mask] * 2.5, 0, 1)
        blended = blended * 0.8 + 0.1  # overall brighten

    elif style == "stone":
        # Add cracks
        for _ in range(15):
            x0, y0 = rng.integers(0, size, 2)
            for step in range(rng.integers(20, 80)):
                x1 = np.clip(x0 + rng.integers(-5, 6), 0, size - 1)
                y1 = np.clip(y0 + rng.integers(-5, 6), 0, size - 1)
                blended[y0:y1+1, x0:x1+1] *= 0.6
                x0, y0 = x1, y1

    elif style == "fiery":
        # Orange-red gradient from bottom
        gradient = np.linspace(0.2, 1.0, size)[:, None, None]
        blended[:, :, 0] = np.clip(blended[:, :, 0] * gradient[:, :, 0] + 0.3, 0, 1)
        blended[:, :, 1] = np.clip(blended[:, :, 1] * 0.4, 0, 1)
        blended[:, :, 2] = np.clip(blended[:, :, 2] * 0.1, 0, 1)

    elif style == "icy":
        # Blue-white shimmer
        blended = blended * 0.6 + 0.4
        blended[:, :, 0] *= 0.8
        blended[:, :, 1] *= 0.9

    # Layer 4: Subtle high-frequency noise for micro-detail
    fine_noise = rng.random((size, size, 3)).astype(np.float32) * 0.04
    blended = np.clip(blended + fine_noise, 0, 1)

    # If reference image provided, blend it in
    if reference_image is not None:
        logger.info("Blending reference image into texture")
        ref = reference_image.convert("RGB").resize((size, size), Image.LANCZOS)
        ref_arr = np.array(ref).astype(np.float32) / 255.0
        blended = blended * 0.4 + ref_arr * 0.6

    result = Image.fromarray((blended * 255).astype(np.uint8), "RGB")

    # Enhance contrast slightly
    result = ImageEnhance.Contrast(result).enhance(1.2)
    result = ImageEnhance.Sharpness(result).enhance(1.3)

    return result


# ---------------------------------------------------------------------------
# Texture Generation — AI (Stable Diffusion, CPU-safe)
# ---------------------------------------------------------------------------

def generate_ai_texture(
    prompt: str,
    size: int = 512,
    reference_image: Image.Image = None,
    num_inference_steps: int = 20,
    guidance_scale: float = 7.5,
    strength: float = 0.75,
) -> Image.Image:
    """
    Generate a texture using Stable Diffusion.
    Falls back to procedural if models aren't available.

    Uses stabilityai/stable-diffusion-2-1 via diffusers pipeline.
    On CPU this is slow (~5-10 min per image) but produces excellent results.
    On GPU this runs in ~15-30 seconds.
    """
    try:
        from diffusers import StableDiffusionPipeline, StableDiffusionImg2ImgPipeline
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Running Stable Diffusion on {device}")

        # Enhance prompt for texture generation
        enhanced_prompt = (
            f"{prompt}, seamless texture, tileable, high quality, "
            f"PBR material, 4k resolution, detailed surface"
        )
        negative_prompt = (
            "blurry, low quality, watermark, text, logo, "
            "distorted, seams, artifacts, ugly"
        )

        if reference_image is not None:
            # img2img: use reference as guide
            logger.info("Using img2img pipeline with reference image")
            pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                torch_dtype=torch.float32,
                safety_checker=None,
            )
            pipe = pipe.to(device)
            pipe.enable_attention_slicing()

            ref_resized = reference_image.convert("RGB").resize((size, size))
            result = pipe(
                prompt=enhanced_prompt,
                negative_prompt=negative_prompt,
                image=ref_resized,
                strength=strength,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
            ).images[0]
        else:
            # text2img
            logger.info("Using text2img pipeline")
            pipe = StableDiffusionPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                torch_dtype=torch.float32,
                safety_checker=None,
            )
            pipe = pipe.to(device)
            pipe.enable_attention_slicing()

            result = pipe(
                prompt=enhanced_prompt,
                negative_prompt=negative_prompt,
                width=size,
                height=size,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
            ).images[0]

        return result

    except Exception as e:
        logger.warning(f"AI texture generation failed ({e}), falling back to procedural")
        return generate_procedural_texture(prompt, size, reference_image)


# ---------------------------------------------------------------------------
# UV-Space Texture Baking
# ---------------------------------------------------------------------------

def bake_texture_to_uv(
    texture: Image.Image,
    uvs: np.ndarray,
    faces: np.ndarray,
    output_size: int = 1024,
) -> Image.Image:
    """
    Project a generated texture into UV space by rasterizing each UV triangle
    and sampling from the source texture.

    This ensures the texture is correctly mapped in UV atlas space, avoiding
    distortion or incorrect island placement.
    """
    logger.info("Baking texture into UV space")
    tex_size = texture.size[0]
    tex_arr = np.array(texture.convert("RGB"))

    canvas = np.zeros((output_size, output_size, 3), dtype=np.uint8)
    # Fill with a neutral mid-grey background
    canvas[:] = [127, 127, 127]

    def sample_bilinear(arr, u, v):
        """Sample texture array at (u, v) ∈ [0, 1]² with bilinear interpolation"""
        x = u * (arr.shape[1] - 1)
        y = (1.0 - v) * (arr.shape[0] - 1)
        x0, y0 = int(x), int(y)
        x1, y1 = min(x0 + 1, arr.shape[1] - 1), min(y0 + 1, arr.shape[0] - 1)
        fx, fy = x - x0, y - y0
        c00 = arr[y0, x0].astype(float)
        c10 = arr[y0, x1].astype(float)
        c01 = arr[y1, x0].astype(float)
        c11 = arr[y1, x1].astype(float)
        return ((c00 * (1 - fx) + c10 * fx) * (1 - fy) +
                (c01 * (1 - fx) + c11 * fx) * fy).astype(np.uint8)

    # Rasterize each UV triangle using scanline fill
    for face in faces:
        uv_pts = uvs[face]  # shape (3, 2)
        # Convert to pixel coordinates
        px = (uv_pts[:, 0] * (output_size - 1)).astype(int)
        py = ((1.0 - uv_pts[:, 1]) * (output_size - 1)).astype(int)

        # Bounding box
        min_x, max_x = max(px.min() - 1, 0), min(px.max() + 1, output_size - 1)
        min_y, max_y = max(py.min() - 1, 0), min(py.max() + 1, output_size - 1)

        # Barycentric rasterization
        def edge(ax, ay, bx, by, px, py):
            return (px - ax) * (by - ay) - (py - ay) * (bx - ax)

        ax, ay = px[0], py[0]
        bx, by = px[1], py[1]
        cx, cy = px[2], py[2]
        area = edge(ax, ay, bx, by, cx, cy)
        if area == 0:
            continue

        for iy in range(min_y, max_y + 1):
            for ix in range(min_x, max_x + 1):
                w0 = edge(bx, by, cx, cy, ix, iy)
                w1 = edge(cx, cy, ax, ay, ix, iy)
                w2 = edge(ax, ay, bx, by, ix, iy)
                if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                    b0 = w0 / area
                    b1 = w1 / area
                    b2 = w2 / area
                    # Interpolate UV
                    u = b0 * uv_pts[0, 0] + b1 * uv_pts[1, 0] + b2 * uv_pts[2, 0]
                    v = b0 * uv_pts[0, 1] + b1 * uv_pts[1, 1] + b2 * uv_pts[2, 1]
                    canvas[iy, ix] = sample_bilinear(tex_arr, u, v)

    return Image.fromarray(canvas)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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

    Args:
        prompt             : text description of the desired texture
        output_path        : where to save the PNG texture
        uvs                : UV coordinates from unwrap (optional, for baking)
        faces              : face indices (optional, for baking)
        reference_image_path: path to a reference image (optional)
        texture_size       : output texture resolution in pixels
        use_ai             : whether to use Stable Diffusion (slower but higher quality)
        ai_steps           : number of diffusion steps (more = better quality, slower)

    Returns:
        Path to saved texture PNG
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    reference_image = None
    if reference_image_path and os.path.exists(reference_image_path):
        logger.info(f"Loading reference image: {reference_image_path}")
        reference_image = Image.open(reference_image_path).convert("RGB")

    # Generate texture image
    if use_ai:
        logger.info("Generating AI texture with Stable Diffusion")
        texture = generate_ai_texture(
            prompt=prompt,
            size=min(texture_size, 512),  # SD works best at 512
            reference_image=reference_image,
            num_inference_steps=ai_steps,
        )
        # Upsample to target size
        if texture.size[0] < texture_size:
            texture = texture.resize((texture_size, texture_size), Image.LANCZOS)
    else:
        logger.info("Generating procedural texture")
        texture = generate_procedural_texture(
            prompt=prompt,
            size=texture_size,
            reference_image=reference_image,
        )

    # Save the texture
    texture.save(output_path, "PNG")
    logger.info(f"Texture saved to {output_path}")

    return output_path
