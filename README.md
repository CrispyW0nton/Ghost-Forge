# UV & Texture Generator

Automatically generate UV maps and textures for existing 3D models.  
Upload any mesh → get back a fully textured, UV-unwrapped model.

> Based on [Modly](https://github.com/lightningpixel/modly) by Lightning Pixel (MIT License)

---

## Features

| Feature | Technology |
|---------|-----------|
| Automatic UV unwrapping | **xatlas** (ABF++ + RBPF atlas packing) |
| Procedural texture generation | Custom PIL-based layered synthesizer |
| AI texture generation | **Stable Diffusion** via 🤗 diffusers |
| Reference image style transfer | SD img2img pipeline |
| 3D preview in browser | **Three.js** + GLTFLoader |
| Supported input formats | OBJ, GLB, GLTF, STL, PLY, DAE |
| Supported output formats | GLB (binary glTF), OBJ + MTL |

---

## How It Works

```
Input Mesh
    │
    ▼
[xatlas UV Unwrap]
    │  ABF++ angle-based flattening
    │  RBPF atlas island packing
    │
    ▼
[Texture Generation]
    │  Procedural (fast, no GPU needed)  OR
    │  Stable Diffusion (AI, better quality)
    │  Reference image blending (optional)
    │
    ▼
[Apply + Export]
    │  Texture baked into UV space
    │  GLB or OBJ output
    ▼
Textured Mesh + Texture PNG + UV Layout PNG
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install xatlas trimesh flask flask-cors pillow numpy scipy open3d
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install diffusers transformers accelerate

# 2. Start the server
cd api
python3 app.py

# 3. Open browser
# http://localhost:5000
```

---

## Project Structure

```
webapp/
├── api/
│   ├── app.py          ← Flask REST API server
│   ├── pipeline.py     ← Main processing pipeline
│   ├── uv_unwrap.py    ← xatlas UV unwrapping module
│   └── texture_gen.py  ← Procedural + AI texture generation
├── static/
│   ├── css/style.css   ← Dark theme UI styles
│   └── js/app.js       ← Frontend app (Three.js + fetch API)
├── templates/
│   └── index.html      ← Main web UI
├── uploads/            ← Uploaded meshes (per job)
└── outputs/            ← Generated files (per job)
```

---

## API Reference

### `POST /api/jobs`
Start a new UV + texture job.

**Form fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mesh` | file | ✓ | 3D model (OBJ/GLB/STL/PLY/DAE) |
| `prompt` | string | ✓ | Texture description |
| `reference` | file | — | Reference image for style |
| `texture_size` | int | — | 512/1024/2048 (default: 1024) |
| `output_format` | string | — | "glb" or "obj" (default: "glb") |
| `use_ai` | bool | — | Use Stable Diffusion (default: false) |
| `ai_steps` | int | — | SD inference steps (default: 20) |

**Response:** `{ "job_id": "...", "status": "queued" }`

### `GET /api/jobs/<job_id>`
Poll job status and results.

### `GET /api/jobs/<job_id>/download/<type>`
Download output files. `type` = `mesh` | `texture` | `uv_layout`

---

## Texture Mode Comparison

| Mode | Speed | Quality | GPU Required |
|------|-------|---------|--------------|
| Procedural | ~0.3s | Good for previewing | No |
| Stable Diffusion (20 steps) | ~5-10min CPU / ~20s GPU | Excellent | Recommended |
| SD + reference image | ~5-10min CPU / ~20s GPU | Best | Recommended |

---

## xatlas UV Unwrapping

xatlas is used by major game studios and is the same algorithm powering many
professional tools. It implements:

- **ABF++ (Angle-Based Flattening)** — minimises angular distortion in each UV island
- **LSCM (Least Squares Conformal Maps)** — conformal parametrization
- **RBPF bin packing** — efficiently packs UV islands into the atlas with configurable padding

The result is a production-quality UV layout with:
- Minimal stretching and distortion
- No overlapping islands
- Configurable padding between islands (prevents texture bleeding)

---

## Credits

- **xatlas** — https://github.com/jpcy/xatlas (MIT)
- **trimesh** — https://github.com/mikedh/trimesh (MIT)
- **diffusers** — https://github.com/huggingface/diffusers (Apache 2.0)
- **Modly** — https://github.com/lightningpixel/modly (MIT) — original inspiration
- **Three.js** — https://threejs.org (MIT)
