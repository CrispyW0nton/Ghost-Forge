/**
 * GhostForge API Client
 * Uses relative /api/* URLs — routed through Vite proxy to Flask on :5000
 * Falls back to absolute localhost:5000 when running outside Vite
 */

// Detect environment: if window.location is localhost:3001 (Vite dev), use relative
// If running in Electron (no Vite proxy), use direct localhost:5000
function getBase() {
  if (typeof window !== 'undefined') {
    const { hostname, port } = window.location
    // Electron renderer — talk directly to backend
    if (hostname === 'localhost' && (port === '' || parseInt(port) > 5000)) {
      return 'http://localhost:5000'
    }
    // Vite dev server — proxy /api through
    if (hostname === 'localhost' || hostname.includes('sandbox')) {
      return ''  // relative — Vite proxy handles it
    }
  }
  return 'http://localhost:5000'
}

const BASE = getBase()

// ─── Generic fetch helper ─────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const url = `${BASE}${path}`
  const res = await fetch(url, options)
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const j = await res.json(); msg = j.error || j.detail || msg } catch (_) {}
    throw new Error(msg)
  }
  return res.json()
}

// ─── Health ───────────────────────────────────────────────────────────────────
export const checkHealth = () => apiFetch('/api/health')

// ─── Mesh info (quick parse without running full pipeline) ─────────────────────
export async function getMeshInfo(meshFile) {
  const form = new FormData()
  form.append('mesh', meshFile)
  return apiFetch('/api/mesh-info', { method: 'POST', body: form })
}

// ─── UV + Texture Jobs ────────────────────────────────────────────────────────
export async function createUVTextureJob({
  meshFile, prompt, referenceFile,
  textureSize, useAI, aiSteps, outputFormat,
  uvOnly = false,
}) {
  const form = new FormData()
  form.append('mesh', meshFile)
  form.append('prompt', prompt || 'worn surface, detailed PBR material')
  form.append('texture_size', textureSize || 1024)
  form.append('use_ai',       useAI ? 'true' : 'false')
  form.append('ai_steps',     aiSteps || 20)
  form.append('output_format', outputFormat || 'glb')
  form.append('uv_only',      uvOnly ? 'true' : 'false')
  if (referenceFile) form.append('reference', referenceFile)

  return apiFetch('/api/jobs', { method: 'POST', body: form })
}

export const getJob         = (id)       => apiFetch(`/api/jobs/${id}`)
export const listJobs       = ()         => apiFetch('/api/jobs')

// Build full download/preview URLs — need absolute base when cross-origin
export function getDownloadUrl(id, type) {
  const base = BASE || 'http://localhost:5000'
  return `${base}/api/jobs/${id}/download/${type}`
}
export function getPreviewUrl(id, type) {
  const base = BASE || 'http://localhost:5000'
  return `${base}/api/jobs/${id}/preview/${type}`
}
export function getGlbPreviewUrl(id) {
  const base = BASE || 'http://localhost:5000'
  return `${base}/api/jobs/${id}/preview/mesh_glb`
}

// ─── Poll job until done ──────────────────────────────────────────────────────
export function pollJob(jobId, onProgress, onDone, onError, intervalMs = 600) {
  const timer = setInterval(async () => {
    try {
      const job = await getJob(jobId)
      onProgress?.(job)
      if (job.status === 'done') {
        clearInterval(timer)
        onDone?.(job)
      } else if (job.status === 'error') {
        clearInterval(timer)
        onError?.(new Error(job.error || 'Job failed'))
      }
    } catch (e) {
      clearInterval(timer)
      onError?.(e)
    }
  }, intervalMs)
  return () => clearInterval(timer)
}

// ─── Image-to-3D (Modly extension system) ────────────────────────────────────
export async function generateMeshFromImage({ imageFile, modelId }) {
  const form = new FormData()
  form.append('image', imageFile)
  form.append('model_id', modelId || 'hunyuan3d-mini')
  return apiFetch('/api/generate', { method: 'POST', body: form })
}

export const listModels     = () => apiFetch('/api/models')
export const listExtensions = () => apiFetch('/api/extensions')

// ─── AI Chat (OpenAI-compatible streaming) ────────────────────────────────────
export async function sendChatMessage({ messages, apiKey, model, baseUrl, signal }) {
  const url = `${baseUrl || 'https://api.openai.com/v1'}/chat/completions`

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: model || 'gpt-4o',
      messages,
      stream: true,
      temperature: 0.7,
      max_tokens: 2048,
    }),
    signal,
  })

  if (!res.ok) {
    let msg = `AI API error ${res.status}`
    try { const j = await res.json(); msg = j.error?.message || msg } catch (_) {}
    throw new Error(msg)
  }

  return streamSSE(res)
}

async function* streamSSE(response) {
  const reader  = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (data === '[DONE]') return
      try {
        const json  = JSON.parse(data)
        const delta = json.choices?.[0]?.delta?.content
        if (delta) yield delta
      } catch (_) {}
    }
  }
}

// ─── MCP / Scene Context ──────────────────────────────────────────────────────
export function buildSceneContext(objects, activeJob) {
  const sceneDesc = objects.length === 0
    ? 'The scene is currently empty.'
    : `The scene contains ${objects.length} object(s):\n` +
      objects.map(o =>
        `- "${o.name}" (${o.type || '3D mesh'})` +
        (o.meshStats ? ` [${o.meshStats.vertices?.toLocaleString()} verts, ${o.meshStats.faces?.toLocaleString()} faces]` : '') +
        (o.uvDone ? ' [UV unwrapped]' : '') +
        (o.textureDone ? ` [textured: ${o.texturePrompt || 'yes'}]` : '') +
        (o.selected ? ' [SELECTED]' : '')
      ).join('\n')

  const jobDesc = activeJob
    ? `\nActive job: ${activeJob.type} — ${activeJob.stage} (${activeJob.progress}%)`
    : ''

  return `You are GHOST AI, an expert 3D modeling and texturing assistant integrated directly into GhostForge — a Matrix-themed 3D creation suite. You have full awareness of the user's scene and can guide them through every workflow step.

GhostForge capabilities:
- UV unwrapping (automatic, xatlas ABF++ algorithm — same quality as RizomUV)
- Texture generation (procedural fast mode OR Stable Diffusion AI mode with reference image support)
- Image-to-3D mesh generation (Hunyuan3D, TripoSG, TRELLIS extensions)
- 3D viewport with orbit/pan/zoom, GLB/OBJ/STL/PLY import
- Export: textured GLB, texture PNG, UV layout PNG, OBJ+MTL

Current scene:
${sceneDesc}${jobDesc}

Be concise, technically precise, and act as a creative partner — not just a helper. When suggesting UV/texture workflows, be specific about settings (atlas size, padding, material prompts). You can see their scene state above.`
}
