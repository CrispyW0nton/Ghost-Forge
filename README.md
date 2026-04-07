# 👻🔥 GhostForge

**Open source 3D creation suite with integrated AI partnership.**

GhostForge combines UV unwrapping, texture generation, image-to-3D mesh generation, and a built-in AI co-creator into one unified workspace. Enter your own API key and your chosen AI works *alongside* you — it can see your scene, understand your workflow, and guide you in real time.

> Based on [Modly](https://github.com/lightningpixel/modly) by Lightning Pixel (MIT License)

---

## Vision

> *"The power should be with the people, not the companies."*

GhostForge is the open-source answer to a suite of tools that should never have been locked behind corporate paywalls:

| Replaces | With |
|---------|------|
| RizomUV | xatlas (ABF++ UV unwrapping) |
| Substance Painter | Stable Diffusion AI texturing |
| Modly / Hunyuan3D | Image → 3D mesh generation |
| Maya/Blender viewport | React Three Fiber 3D workspace |
| No equivalent existed | AI partner with full scene context |

---

## Features

### ✅ Built (Phase 1)
- **Automatic UV unwrapping** — xatlas ABF++ algorithm, production quality
- **Procedural texture generation** — instant, no GPU needed, keyword-driven
- **AI texture generation** — Stable Diffusion via diffusers
- **Reference image style transfer** — SD img2img pipeline
- **Image-to-3D** — Hunyuan3D / TripoSG / TRELLIS extension system (from Modly)
- **3D viewport** — React Three Fiber + OrbitControls
- **AI chat panel** — streaming, real-time, scene-aware
- **API key settings** — OpenAI / Anthropic / Ollama / any OpenAI-compatible
- **Scene hierarchy** — import, list, select, remove objects
- **Properties panel** — UV controls, texture controls, per-object settings

### 🔜 Roadmap (Phase 2+)
- PBR texture painter (paint directly on mesh)
- Auto-rigging (RigNet / AccuRIG-equivalent)
- Sculpting tools (OpenVDB / libigl)
- MCP tool calls (AI can directly trigger unwrap/texture/export)
- Extension system (install AI models from GitHub like Modly)
- Packaged desktop builds (Windows / Linux / macOS via Electron)

---

## Stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | Electron 33 |
| UI framework | React 18 + Vite + Tailwind |
| 3D viewport | React Three Fiber + Three.js |
| State management | Zustand (persisted settings) |
| Python backend | Flask + FastAPI |
| UV unwrapping | xatlas (ABF++ + RBPF packing) |
| Mesh processing | trimesh + PyMeshLab |
| AI texturing | Stable Diffusion via diffusers |
| AI chat | OpenAI-compatible streaming API |

---

## Quick Start

```bash
# 1. Install Python dependencies
pip install xatlas trimesh flask flask-cors pillow numpy scipy open3d
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install diffusers transformers accelerate

# 2. Start Python backend
cd api && python3 app.py

# 3. Install JS dependencies
npm install

# 4. Run the app (web preview)
npx vite --config vite.web.config.js

# 5. Or package as desktop app
npm run package
```

---

## AI Integration

GhostForge uses a fully open API key system. In Settings, enter:
- Your API key (OpenAI, Anthropic, Together AI, or any provider)
- Your chosen model (GPT-4o, Claude, Llama, Mistral, etc.)
- The API base URL (works with Ollama for 100% local/offline AI)

The AI receives your **full scene context** automatically — which models are loaded, which are selected, UV and texture status. It's not "ask AI to do everything" — it's a genuine creative partner that can see what you're working on and help you make decisions.

---

## Credits

- **xatlas** — https://github.com/jpcy/xatlas (MIT)
- **trimesh** — https://github.com/mikedh/trimesh (MIT)
- **diffusers** — https://github.com/huggingface/diffusers (Apache 2.0)
- **Modly** — https://github.com/lightningpixel/modly (MIT) — image-to-3D extension system
- **React Three Fiber** — https://github.com/pmndrs/react-three-fiber (MIT)
- **Three.js** — https://threejs.org (MIT)
- **Zustand** — https://github.com/pmndrs/zustand (MIT)
