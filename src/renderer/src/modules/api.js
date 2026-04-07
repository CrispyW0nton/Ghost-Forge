/**
 * GhostForge API Client
 * Talks to the Python FastAPI/Flask backend on localhost:5000
 * Also handles calls to external AI APIs (OpenAI-compatible)
 */

const BASE = 'http://localhost:5000'

// ─── Generic fetch helper ──────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const j = await res.json(); msg = j.error || j.detail || msg } catch (_) {}
    throw new Error(msg)
  }
  return res.json()
}

// ─── Health ───────────────────────────────────────────────────────────────────
export const checkHealth = () => apiFetch('/api/health')

// ─── UV + Texture Jobs ────────────────────────────────────────────────────────
export async function createUVTextureJob({ meshFile, prompt, referenceFile, textureSize, useAI, aiSteps, outputFormat }) {
  const form = new FormData()
  form.append('mesh', meshFile)
  form.append('prompt', prompt || 'worn surface, detailed PBR material')
  form.append('texture_size', textureSize || 1024)
  form.append('use_ai', useAI ? 'true' : 'false')
  form.append('ai_steps', aiSteps || 20)
  form.append('output_format', outputFormat || 'glb')
  if (referenceFile) form.append('reference', referenceFile)

  return apiFetch('/api/jobs', { method: 'POST', body: form })
}

export const getJob        = (id)   => apiFetch(`/api/jobs/${id}`)
export const listJobs      = ()     => apiFetch('/api/jobs')
export const getDownloadUrl = (id, type) => `${BASE}/api/jobs/${id}/download/${type}`
export const getPreviewUrl  = (id, type) => `${BASE}/api/jobs/${id}/preview/${type}`

// ─── Poll a job until done ─────────────────────────────────────────────────────
export function pollJob(jobId, onProgress, onDone, onError, intervalMs = 800) {
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
  return () => clearInterval(timer)  // return cancel fn
}

// ─── Image-to-3D (Modly extension system) ────────────────────────────────────
export async function generateMeshFromImage({ imageFile, modelId }) {
  const form = new FormData()
  form.append('image', imageFile)
  form.append('model_id', modelId || 'hunyuan3d-mini')
  return apiFetch('/api/generate', { method: 'POST', body: form })
}

export const listModels      = ()  => apiFetch('/api/models')
export const listExtensions  = ()  => apiFetch('/api/extensions')

// ─── AI Chat (OpenAI-compatible) ──────────────────────────────────────────────
/**
 * Send a chat completion request to any OpenAI-compatible API.
 * Works with OpenAI, Anthropic (via compatible proxy), Ollama, etc.
 */
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

  // Return async generator that yields streamed content chunks
  return streamSSE(res)
}

async function* streamSSE(response) {
  const reader = response.body.getReader()
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
        const json = JSON.parse(data)
        const delta = json.choices?.[0]?.delta?.content
        if (delta) yield delta
      } catch (_) {}
    }
  }
}

// ─── MCP Scene Context ────────────────────────────────────────────────────────
/**
 * Build a scene context object to inject into AI system prompt.
 * This gives the AI awareness of what's in the scene — the "MCP" awareness.
 */
export function buildSceneContext(objects, activeJob) {
  const sceneDesc = objects.length === 0
    ? 'The scene is currently empty.'
    : `The scene contains ${objects.length} object(s):\n` +
      objects.map(o =>
        `- "${o.name}" (${o.type || '3D mesh'})` +
        (o.uvDone ? ' [UV unwrapped]' : '') +
        (o.textureDone ? ` [textured: ${o.texturePrompt || 'yes'}]` : '') +
        (o.selected ? ' [SELECTED]' : '')
      ).join('\n')

  const jobDesc = activeJob
    ? `\nActive job: ${activeJob.type} — ${activeJob.stage} (${activeJob.progress}%)`
    : ''

  return `You are GhostForge AI, an expert 3D modeling and texturing assistant integrated directly into the GhostForge 3D creation suite. You can see the user's scene and help them work on their models.

GhostForge capabilities you can guide the user to use:
- UV unwrapping (automatic, xatlas ABF++ algorithm)
- Texture generation (procedural or Stable Diffusion AI, with optional reference image)
- Image-to-3D mesh generation (via Hunyuan3D, TripoSG, TRELLIS extensions)
- 3D viewport with orbit/pan/zoom controls
- Model import/export (OBJ, GLB, GLTF, STL, PLY)

Current scene state:
${sceneDesc}${jobDesc}

When the user asks you to perform actions (unwrap UVs, generate texture, import model, etc.), describe what steps to take or what settings to use. Be concise, direct, and technically accurate. You are their creative partner, not just an assistant.`
}
