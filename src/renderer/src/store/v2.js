/**
 * Zustand stores for the v2 domains.
 *
 * Each store is intentionally narrow: it caches the last result, tracks
 * loading + error state, and exposes a few `refresh*` actions that
 * panels call. The pattern is uniform so adding a new domain (e.g.
 * benchmarks in P11) needs ~30 lines.
 *
 * Naming: stores live under `useXxxStore` with the same casing as the
 * apiV2 namespaces — `useWorkersStore`, `useRuntimeStore`, etc.
 */

import { create } from 'zustand'
import { Audit, Authoring, Engines, KB, Models, Retarget, Runtime, Slices, Workers } from '../modules/apiV2'

// ─── Runtime store: GPUs + scheduler + loaded sessions ────────────────────────
export const useRuntimeStore = create((set, get) => ({
  gpus: null,
  scheduler: null,
  sessions: [],
  loading: false,
  error: null,

  refresh: async ({ refreshGpus = false } = {}) => {
    set({ loading: true, error: null })
    try {
      const [gpus, scheduler, sessions] = await Promise.all([
        Runtime.gpus({ refresh: refreshGpus }),
        Runtime.scheduler(),
        Runtime.sessions(),
      ])
      set({ gpus, scheduler, sessions, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  freeAllSessions: async () => {
    try {
      await Runtime.freeSession({ force: true })
      const sessions = await Runtime.sessions()
      set({ sessions })
    } catch (err) {
      set({ error: err.message })
    }
  },
}))

// ─── Workers store: registry + probe results ──────────────────────────────────
export const useWorkersStore = create((set, get) => ({
  entries: [],
  loading: false,
  error: null,

  refresh: async () => {
    set({ loading: true, error: null })
    try {
      const entries = await Workers.list()
      set({ entries, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  // Returns the cached descriptor + probe payload for a single worker.
  byName: (name) =>
    get().entries.find((e) => e.descriptor?.name === name) || null,

  // Returns workers that currently advertise a given capability and
  // (optionally) only the runnable ones.
  forCapability: (capability, { onlyRunnable = false } = {}) =>
    get().entries.filter((e) => {
      const caps = e.descriptor?.capabilities || []
      if (!caps.includes(capability)) return false
      if (onlyRunnable && !e.probe?.runnable) return false
      return true
    }),
}))

// ─── Models store: artifact registry + cache state ────────────────────────────
export const useModelsStore = create((set) => ({
  entries: [],
  loading: false,
  error: null,
  downloading: {},  // model_id -> true while downloading

  refresh: async () => {
    set({ loading: true, error: null })
    try {
      const entries = await Models.list()
      set({ entries, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  download: async (modelId) => {
    set((s) => ({ downloading: { ...s.downloading, [modelId]: true } }))
    try {
      await Models.download(modelId)
      const entries = await Models.list()
      set((s) => {
        const next = { ...s.downloading }
        delete next[modelId]
        return { entries, downloading: next }
      })
    } catch (err) {
      set((s) => {
        const next = { ...s.downloading }
        delete next[modelId]
        return { error: err.message, downloading: next }
      })
      throw err
    }
  },

  clear: async (modelId) => {
    try {
      await Models.clear(modelId)
      const entries = await Models.list()
      set({ entries })
    } catch (err) {
      set({ error: err.message })
    }
  },
}))

// ─── KB store: concepts + last search ─────────────────────────────────────────
export const useKbStore = create((set, get) => ({
  concepts: [],
  searchResults: [],
  searchQuery: '',
  loading: false,
  error: null,

  refreshConcepts: async () => {
    set({ loading: true, error: null })
    try {
      const concepts = await KB.list({ limit: 200 })
      set({ concepts, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  search: async (query, opts = {}) => {
    set({ loading: true, error: null, searchQuery: query })
    try {
      const searchResults = await KB.search({ query, ...opts })
      set({ searchResults, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  ingest: async (params) => {
    set({ loading: true, error: null })
    try {
      const entry = await KB.ingestLocal(params)
      const concepts = await KB.list({ limit: 200 })
      set({ concepts, loading: false })
      return entry
    } catch (err) {
      set({ error: err.message, loading: false })
      throw err
    }
  },
}))

// ─── Audit store: presets + last run report ───────────────────────────────────
export const useAuditStore = create((set) => ({
  presets: null,
  lastReport: null,
  lastAssetDir: null,
  loading: false,
  error: null,

  loadPresets: async () => {
    try {
      const presets = await Audit.presets()
      set({ presets })
    } catch (err) {
      set({ error: err.message })
    }
  },

  run: async ({ assetDir, preset = 'default', runGltfValidator = false }) => {
    set({ loading: true, error: null, lastAssetDir: assetDir })
    try {
      const lastReport = await Audit.run({ assetDir, preset, runGltfValidator })
      set({ lastReport, loading: false })
      return lastReport
    } catch (err) {
      set({ error: err.message, loading: false })
      throw err
    }
  },

  clear: () => set({ lastReport: null, lastAssetDir: null, error: null }),
}))

// ─── Engines store: adapters + handoff history ────────────────────────────────
export const useEnginesStore = create((set) => ({
  adapters: [],
  handoffs: [],   // [{ engine, assetDir, result, ts }]
  bridges: [],    // [{ engine, assetDir, result, ts }]
  loading: false,
  error: null,

  refresh: async () => {
    set({ loading: true, error: null })
    try {
      const adapters = await Engines.list()
      set({ adapters, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  configure: async (name, config) => {
    try {
      await Engines.configure(name, config)
      const adapters = await Engines.list()
      set({ adapters })
    } catch (err) {
      set({ error: err.message })
      throw err
    }
  },

  send: async (name, payload) => {
    set({ loading: true, error: null })
    try {
      const result = await Engines.send(name, payload)
      set((s) => ({
        handoffs: [
          { engine: name, assetDir: payload.asset_dir, result, ts: Date.now() },
          ...s.handoffs,
        ].slice(0, 50),
        loading: false,
      }))
      return result
    } catch (err) {
      set({ error: err.message, loading: false })
      throw err
    }
  },

  exportBridge: async (name, payload) => {
    set({ loading: true, error: null })
    try {
      const result = await Engines.exportBridge(name, payload)
      set((s) => ({
        bridges: [
          { engine: name, assetDir: payload.asset_dir, result, ts: Date.now() },
          ...s.bridges,
        ].slice(0, 50),
        loading: false,
      }))
      return result
    } catch (err) {
      set({ error: err.message, loading: false })
      throw err
    }
  },
}))

// ─── Slices store: planner + execution state ─────────────────────────────────
export const useSlicesStore = create((set, get) => ({
  summaries: [],
  active: null,           // { plan, run } currently selected slice
  loading: false,
  executing: false,
  error: null,

  refresh: async () => {
    set({ loading: true, error: null })
    try {
      const summaries = await Slices.list()
      set({ summaries, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  open: async (sliceId) => {
    set({ loading: true, error: null })
    try {
      const active = await Slices.get(sliceId)
      set({ active, loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  create: async (params) => {
    set({ loading: true, error: null })
    try {
      const plan = await Slices.create(params)
      const summaries = await Slices.list()
      set({ summaries, active: { plan, run: null }, loading: false })
      return plan
    } catch (err) {
      set({ error: err.message, loading: false })
      throw err
    }
  },

  execute: async (sliceId) => {
    set({ executing: true, error: null })
    try {
      const run = await Slices.execute(sliceId)
      const active = await Slices.get(sliceId)
      set({ active, executing: false })
      return run
    } catch (err) {
      set({ error: err.message, executing: false })
      throw err
    }
  },

  remove: async (sliceId) => {
    try {
      await Slices.delete(sliceId)
      const summaries = await Slices.list()
      const { active } = get()
      const cleared = active?.plan?.slice_id === sliceId
      set({ summaries, active: cleared ? null : active })
    } catch (err) {
      set({ error: err.message })
    }
  },
}))

// ─── Authoring store: operations + edit graphs (P11) ─────────────────────────
//
// Two halves: a process-wide cache of the operation palette (loaded once
// from the server, since it never changes mid-session) and per-session
// state for the currently-open edit graph + its last evaluation report.
//
// Mutating actions (append/update/remove/reorder/evaluate) talk directly
// to the v2 endpoints and re-fetch the active graph so the UI never
// renders stale stack state. The `summaries` field powers the graph
// list dropdown without paying for a full per-graph fetch.
export const useAuthoringStore = create((set, get) => ({
  operations: [],
  summaries: [],
  active: null,
  loadingOps: false,
  loadingGraph: false,
  evaluating: false,
  error: null,

  refreshOperations: async () => {
    set({ loadingOps: true, error: null })
    try {
      const body = await Authoring.operations()
      set({ operations: body.operations || [], loadingOps: false })
    } catch (err) {
      set({ error: err.message, loadingOps: false })
    }
  },

  refreshGraphs: async () => {
    try {
      const body = await Authoring.listGraphs()
      set({ summaries: body.graphs || [] })
    } catch (err) {
      set({ error: err.message })
    }
  },

  open: async (graphId) => {
    set({ loadingGraph: true, error: null })
    try {
      const body = await Authoring.getGraph(graphId)
      set({
        active: { graph: body.graph, evaluation: body.evaluation || null },
        loadingGraph: false,
      })
    } catch (err) {
      set({ error: err.message, loadingGraph: false })
    }
  },

  create: async (payload) => {
    set({ error: null })
    try {
      const graph = await Authoring.createGraph(payload || {})
      const summaries = (await Authoring.listGraphs()).graphs || []
      set({ summaries, active: { graph, evaluation: null } })
      return graph
    } catch (err) {
      set({ error: err.message })
      throw err
    }
  },

  remove: async (graphId) => {
    try {
      await Authoring.deleteGraph(graphId)
      const summaries = (await Authoring.listGraphs()).graphs || []
      const { active } = get()
      const cleared = active?.graph?.graph_id === graphId
      set({ summaries, active: cleared ? null : active })
    } catch (err) {
      set({ error: err.message })
    }
  },

  appendNode: async (graphId, node) => {
    try {
      const graph = await Authoring.appendNode(graphId, node)
      set({ active: { graph, evaluation: get().active?.evaluation || null } })
      return graph
    } catch (err) {
      set({ error: err.message })
      throw err
    }
  },

  updateNode: async (graphId, nodeId, patch) => {
    try {
      const graph = await Authoring.updateNode(graphId, nodeId, patch)
      set({ active: { graph, evaluation: get().active?.evaluation || null } })
      return graph
    } catch (err) {
      set({ error: err.message })
      throw err
    }
  },

  removeNode: async (graphId, nodeId) => {
    try {
      const graph = await Authoring.removeNode(graphId, nodeId)
      set({ active: { graph, evaluation: get().active?.evaluation || null } })
      return graph
    } catch (err) {
      set({ error: err.message })
      throw err
    }
  },

  reorderNodes: async (graphId, order) => {
    try {
      const graph = await Authoring.reorderNodes(graphId, order)
      set({ active: { graph, evaluation: get().active?.evaluation || null } })
      return graph
    } catch (err) {
      set({ error: err.message })
      throw err
    }
  },

  evaluate: async (graphId, options = {}) => {
    set({ evaluating: true, error: null })
    try {
      const evaluation = await Authoring.evaluate(graphId, options)
      const refreshed = await Authoring.getGraph(graphId)
      set({
        active: { graph: refreshed.graph, evaluation },
        evaluating: false,
      })
      return evaluation
    } catch (err) {
      set({ error: err.message, evaluating: false })
      throw err
    }
  },
}))

// ─── Retarget store: cross-engine linting + planner (P12) ────────────────────
//
// Two pieces of state:
//   * `profiles` — the engine profile registry, fetched once.
//   * `lastReport` / `lastGraph` — cached output of the most recent
//     `lint` or `plan` call so the AuditTab UI can show the diagnostics
//     and the AUTO-RETARGET button can flip into the MODS tab with a
//     pre-populated graph without needing an extra round-trip.
//
// `plan` calls `persistGraph: true` so the resulting graph immediately
// shows up in the modifier-stack picker; the caller is responsible
// for switching the right tab.
export const useRetargetStore = create((set, get) => ({
  profiles: [],
  lastReport: null,
  lastGraph: null,
  loading: false,
  planning: false,
  error: null,

  refreshProfiles: async () => {
    set({ loading: true, error: null })
    try {
      const body = await Retarget.profiles()
      set({ profiles: body.profiles || [], loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  lint: async ({ assetDir, targetEngine, runGltfValidator = false } = {}) => {
    set({ loading: true, error: null })
    try {
      const report = await Retarget.lint({ assetDir, targetEngine, runGltfValidator })
      set({ lastReport: report, loading: false })
      return report
    } catch (err) {
      set({ error: err.message, loading: false })
      throw err
    }
  },

  plan: async ({ assetDir, targetEngine, baseName = null, persistGraph = true } = {}) => {
    set({ planning: true, error: null })
    try {
      const body = await Retarget.plan({ assetDir, targetEngine, baseName, persistGraph })
      set({ lastReport: body.report, lastGraph: body.graph, planning: false })
      return body
    } catch (err) {
      set({ error: err.message, planning: false })
      throw err
    }
  },

  clear: () => set({ lastReport: null, lastGraph: null, error: null }),
}))
