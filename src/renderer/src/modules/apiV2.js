/**
 * GhostForge HTTP API v2 client.
 *
 * Mirrors the `/api/v2/*` Flask blueprint that bridges the desktop UI
 * to the new core (workers, KB, audit, engines, slices, GPU runtime,
 * models, sessions). Each export below targets exactly one endpoint —
 * stores layer composition on top.
 *
 * Why a separate module from `api.js`:
 *   - `api.js` is the legacy v1 surface (mesh-info / jobs / preview
 *     URLs) and is still used by the existing UI panels we haven't
 *     ported yet. Splitting v2 keeps mistakes obvious — a panel
 *     either talks to the legacy mock surface or the new real one.
 */

function getBase() {
  if (typeof window !== 'undefined') {
    const { hostname, port } = window.location
    if (hostname === 'localhost' && (port === '' || parseInt(port, 10) > 5000)) {
      return 'http://localhost:5000'
    }
    if (hostname === 'localhost' || hostname.includes('sandbox')) {
      return ''
    }
  }
  return 'http://localhost:5000'
}

const BASE = getBase()
const V2 = `${BASE}/api/v2`

class ApiError extends Error {
  constructor(code, message, status, payload) {
    super(message || code || `HTTP ${status}`)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.payload = payload
  }
}

async function fetchJson(path, options = {}) {
  const url = path.startsWith('http') ? path : `${V2}${path}`
  const res = await fetch(url, options)
  let body = null
  try { body = await res.json() } catch (_) {}

  if (!res.ok) {
    const code = body?.error || `HTTP_${res.status}`
    const msg = body?.message || res.statusText
    throw new ApiError(code, msg, res.status, body)
  }
  return body
}

function postJson(path, body) {
  return fetchJson(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body == null ? '{}' : JSON.stringify(body),
  })
}

// ─── Runtime ──────────────────────────────────────────────────────────────────
export const Runtime = {
  gpus: ({ refresh = false } = {}) =>
    fetchJson(`/runtime/gpus${refresh ? '?refresh=true' : ''}`),
  scheduler: () => fetchJson('/runtime/scheduler'),
  sessions: () => fetchJson('/runtime/sessions'),
  freeSession: ({ name = null, force = false, idleForSeconds = null } = {}) =>
    postJson('/runtime/sessions/free', {
      name,
      force,
      idle_for_seconds: idleForSeconds,
    }),
}

// ─── Workers ──────────────────────────────────────────────────────────────────
export const Workers = {
  list: () => fetchJson('/workers'),
  probe: (name) => fetchJson(`/workers/${encodeURIComponent(name)}/probe`),
  run: ({ capability, spec }) => postJson('/workers/run', { capability, spec }),
}

// ─── Models ───────────────────────────────────────────────────────────────────
export const Models = {
  list: () => fetchJson('/models'),
  status: (modelId) => fetchJson(`/models/${encodeURIComponent(modelId)}/status`),
  download: (modelId) => postJson(`/models/${encodeURIComponent(modelId)}/download`),
  clear: (modelId) => postJson(`/models/${encodeURIComponent(modelId)}/clear`),
}

// ─── Knowledge base ───────────────────────────────────────────────────────────
export const KB = {
  list: ({ limit = 50, offset = 0, sources = [] } = {}) => {
    const params = new URLSearchParams()
    params.set('limit', limit)
    params.set('offset', offset)
    sources.forEach((s) => params.append('source', s))
    return fetchJson(`/kb/concepts?${params}`)
  },
  search: ({ query, k = 5, sources = [], tags = null } = {}) =>
    postJson('/kb/search', { query, k, sources, tags }),
  ingestLocal: ({ imageFile, license, title, attribution, tags }) => {
    const form = new FormData()
    form.append('image', imageFile)
    form.append('license', license)
    if (title) form.append('title', title)
    if (attribution) form.append('attribution', attribution)
    if (tags && tags.length) form.append('tags', tags.join(','))
    return fetchJson('/kb/ingest/local', { method: 'POST', body: form })
  },
  cite: ({ assetDir, conceptIds, note }) =>
    postJson('/kb/cite', {
      asset_dir: assetDir,
      concept_ids: conceptIds,
      note: note || null,
    }),
}

// ─── Audit ────────────────────────────────────────────────────────────────────
export const Audit = {
  presets: () => fetchJson('/audit/presets'),
  run: ({ assetDir, preset = 'default', runGltfValidator = false }) =>
    postJson('/audit/run', {
      asset_dir: assetDir,
      preset,
      run_gltf_validator: runGltfValidator,
    }),
  manifest: (assetDir) =>
    fetchJson(`/audit/manifest?asset_dir=${encodeURIComponent(assetDir)}`),
}

// ─── Engines ──────────────────────────────────────────────────────────────────
export const Engines = {
  list: () => fetchJson('/engines'),
  configure: (name, config) =>
    postJson(`/engines/${encodeURIComponent(name)}/configure`, config),
  send: (name, payload) =>
    postJson(`/engines/${encodeURIComponent(name)}/send`, payload),
  exportBridge: (name, payload) =>
    postJson(`/engines/${encodeURIComponent(name)}/export-bridge`, payload),
}

// ─── Slices ───────────────────────────────────────────────────────────────────
export const Slices = {
  list: () => fetchJson('/slices'),
  get: (sliceId) => fetchJson(`/slices/${encodeURIComponent(sliceId)}`),
  create: ({ brief, assets, sliceId, failFast = false, skipAudit = false, skipHandoff = false }) =>
    postJson('/slices', {
      brief,
      assets,
      slice_id: sliceId || null,
      fail_fast: failFast,
      skip_audit: skipAudit,
      skip_handoff: skipHandoff,
    }),
  updateAssets: (sliceId, assets) =>
    postJson(`/slices/${encodeURIComponent(sliceId)}/assets`, { assets }),
  delete: (sliceId) =>
    fetchJson(`/slices/${encodeURIComponent(sliceId)}`, { method: 'DELETE' }),
  execute: (sliceId) =>
    postJson(`/slices/${encodeURIComponent(sliceId)}/execute`),
}

// ─── Retarget (P12) ───────────────────────────────────────────────────────────
export const Retarget = {
  profiles: () => fetchJson('/retarget/profiles'),
  lint: ({ assetDir, targetEngine, runGltfValidator = false } = {}) =>
    postJson('/retarget/lint', {
      asset_dir: assetDir,
      target_engine: targetEngine,
      run_gltf_validator: runGltfValidator,
    }),
  plan: ({ assetDir, targetEngine, baseName = null, outputPath = null, persistGraph = false } = {}) =>
    postJson('/retarget/plan', {
      asset_dir: assetDir,
      target_engine: targetEngine,
      base_name: baseName,
      output_path: outputPath,
      persist_graph: persistGraph,
    }),
}

// ─── Authoring (P11) ──────────────────────────────────────────────────────────
export const Authoring = {
  operations: () => fetchJson('/operations'),
  listGraphs: () => fetchJson('/graphs'),
  getGraph: (graphId) => fetchJson(`/graphs/${encodeURIComponent(graphId)}`),
  createGraph: (payload) => postJson('/graphs', payload || {}),
  updateGraph: (graphId, payload) =>
    fetchJson(`/graphs/${encodeURIComponent(graphId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    }),
  deleteGraph: (graphId) =>
    fetchJson(`/graphs/${encodeURIComponent(graphId)}`, { method: 'DELETE' }),
  appendNode: (graphId, node) =>
    postJson(`/graphs/${encodeURIComponent(graphId)}/nodes`, node),
  updateNode: (graphId, nodeId, patch) =>
    fetchJson(
      `/graphs/${encodeURIComponent(graphId)}/nodes/${encodeURIComponent(nodeId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch || {}),
      },
    ),
  removeNode: (graphId, nodeId) =>
    fetchJson(
      `/graphs/${encodeURIComponent(graphId)}/nodes/${encodeURIComponent(nodeId)}`,
      { method: 'DELETE' },
    ),
  reorderNodes: (graphId, order) =>
    postJson(`/graphs/${encodeURIComponent(graphId)}/reorder`, { order }),
  evaluate: (graphId, options = {}) =>
    postJson(`/graphs/${encodeURIComponent(graphId)}/evaluate`, options),
}

export { ApiError }
