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
export const useSceneStore = create((set, get) => ({
  // Loaded objects in the scene
  objects: [],           // [{ id, name, type, mesh, visible, selected, uvDone, textureDone }]
  selectedIds: [],       // currently selected object ids

  // Active job tracking
  activeJob: null,       // { id, type, status, progress, stage }

  // Viewport state
  viewportMode: '3d',    // '3d' | 'uv' | 'texture'
  cameraPreset: 'persp', // 'persp' | 'front' | 'side' | 'top'

  // Scene actions
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
  activeLeftTab:    'scene',     // 'scene' | 'tools' | 'generate'
  activeRightTab:   'properties',// 'properties' | 'uv' | 'texture'

  toggleLeftPanel:  () => set(s => ({ leftPanelOpen: !s.leftPanelOpen })),
  toggleRightPanel: () => set(s => ({ rightPanelOpen: !s.rightPanelOpen })),
  toggleChatPanel:  () => set(s => ({ chatPanelOpen: !s.chatPanelOpen })),
  toggleSettings:   () => set(s => ({ settingsOpen: !s.settingsOpen })),
  setLeftTab:       (t) => set({ activeLeftTab: t }),
  setRightTab:      (t) => set({ activeRightTab: t }),
}))
