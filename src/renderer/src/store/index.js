import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// ─── Settings store (persisted to localStorage) ───────────────────────────────
export const useSettingsStore = create(
  persist(
    (set, get) => ({
      // AI settings
      aiApiKey:       '',
      aiModel:        'gpt-4o',
      aiBaseUrl:      'https://api.openai.com/v1',
      aiProvider:     'openai',   // openai | anthropic | ollama | custom

      // Appearance
      theme:          'dark',
      accentColor:    'forge',    // forge | ghost | both

      // Viewport
      viewportGrid:       true,
      viewportWireframe:  false,
      viewportShadows:    true,
      viewportAA:         true,

      // UV / Texture defaults
      defaultTextureSize: 1024,
      defaultPadding:     2,

      // Actions
      setAiApiKey:    (k) => set({ aiApiKey: k }),
      setAiModel:     (m) => set({ aiModel: m }),
      setAiBaseUrl:   (u) => set({ aiBaseUrl: u }),
      setAiProvider:  (p) => set({ aiProvider: p }),
      setTheme:       (t) => set({ theme: t }),
      toggleGrid:     ()  => set(s => ({ viewportGrid: !s.viewportGrid })),
      toggleWireframe:()  => set(s => ({ viewportWireframe: !s.viewportWireframe })),
    }),
    { name: 'ghostforge-settings' }
  )
)

// ─── Scene store (runtime, not persisted) ─────────────────────────────────────
//
// Each scene object can carry a ``graphId`` linking it to an authoring
// EditGraph. Transform gizmos in the viewport call ``writeTransformToGraph``
// to persist the manipulated translate/rotate/scale into a transform
// modifier node on that graph, so the same edit shows up in the MODS
// tab and round-trips through the evaluator.
export const useSceneStore = create((set, get) => ({
  objects: [],
  selectedIds: [],

  activeJob: null,

  viewportMode: '3d',
  cameraPreset: 'persp',

  // Gizmo + binding
  transformMode: 'translate',  // 'translate' | 'rotate' | 'scale' | null (off)
  transformSpace: 'world',     // 'world' | 'local'

  addObject: (obj) => set(s => ({ objects: [...s.objects, obj] })),
  removeObject: (id) => set(s => ({ objects: s.objects.filter(o => o.id !== id) })),
  updateObject: (id, patch) => set(s => ({
    objects: s.objects.map(o => o.id === id ? { ...o, ...patch } : o)
  })),
  selectObject: (id, multi = false) => set(s => ({
    selectedIds: multi
      ? s.selectedIds.includes(id)
        ? s.selectedIds.filter(i => i !== id)
        : [...s.selectedIds, id]
      : [id]
  })),
  clearSelection: () => set({ selectedIds: [] }),

  setActiveJob: (job)    => set({ activeJob: job }),
  clearActiveJob: ()     => set({ activeJob: null }),
  setViewportMode: (m)   => set({ viewportMode: m }),
  setCameraPreset: (p)   => set({ cameraPreset: p }),

  setTransformMode:  (m) => set({ transformMode: m }),
  setTransformSpace: (s) => set({ transformSpace: s }),

  bindGraphToObject: (objectId, graphId) =>
    set(s => ({
      objects: s.objects.map(o =>
        o.id === objectId ? { ...o, graphId } : o
      ),
    })),

  // Persist a transform delta into both the local object and (if bound)
  // the linked authoring graph. Call from the gizmo's onChange/onPointerUp.
  writeTransformToGraph: async (objectId, transform) => {
    const obj = get().objects.find(o => o.id === objectId)
    if (!obj) return

    set(s => ({
      objects: s.objects.map(o =>
        o.id === objectId ? { ...o, transform: { ...o.transform, ...transform } } : o
      ),
    }))

    if (!obj.graphId) return

    // Lazy import to avoid a hard dep cycle with the authoring store.
    try {
      const { Authoring } = await import('../modules/apiV2.js')
      const graph = await Authoring.getGraph(obj.graphId)
      const existing = (graph?.nodes || []).find(
        n => n.kind === 'transform' && n.label === '__viewport_gizmo__'
      )
      const params = {
        translate: transform.translate || [0, 0, 0],
        rotate_euler_deg: transform.rotate_euler_deg || [0, 0, 0],
        scale: transform.scale || 1.0,
      }
      if (existing) {
        await Authoring.updateNode(obj.graphId, existing.id, { params })
      } else {
        await Authoring.appendNode(obj.graphId, {
          kind: 'transform',
          label: '__viewport_gizmo__',
          params,
        })
      }
    } catch (err) {
      // Surface as a non-fatal warning via the chat store.
      try {
        useChatStore.getState().setError(`viewport gizmo write failed: ${err.message || err}`)
      } catch {}
    }
  },
}))

// ─── Chat store (AI conversation) ─────────────────────────────────────────────
export const useChatStore = create((set, get) => ({
  messages: [],     // [{ id, role: 'user'|'assistant'|'system', content, timestamp }]
  isLoading: false,
  error: null,

  addMessage: (msg) => set(s => ({
    messages: [...s.messages, { id: Date.now(), timestamp: new Date().toISOString(), ...msg }]
  })),
  setLoading: (v) => set({ isLoading: v }),
  setError: (e)   => set({ error: e }),
  clearChat: ()   => set({ messages: [], error: null }),
}))

// ─── UI store (panel visibility, layout) ──────────────────────────────────────
export const useUIStore = create((set) => ({
  leftPanelOpen:    true,
  rightPanelOpen:   true,
  chatPanelOpen:    true,
  settingsOpen:     false,
  activeLeftTab:    'scene',     // 'scene' | 'tools' | 'generate' | 'forge'
  activeRightTab:   'properties',// 'properties' | 'uv' | 'texture' | 'modifiers' | 'audit' | 'engine'

  toggleLeftPanel:  () => set(s => ({ leftPanelOpen: !s.leftPanelOpen })),
  toggleRightPanel: () => set(s => ({ rightPanelOpen: !s.rightPanelOpen })),
  toggleChatPanel:  () => set(s => ({ chatPanelOpen: !s.chatPanelOpen })),
  toggleSettings:   () => set(s => ({ settingsOpen: !s.settingsOpen })),
  setLeftTab:       (t) => set({ activeLeftTab: t }),
  setRightTab:      (t) => set({ activeRightTab: t }),
}))
