import React from 'react'
import { useUIStore, useSceneStore, useSettingsStore } from '../store'

const tools = [
  { id: 'select',    icon: '⬡', label: 'Select',    key: 'Q' },
  { id: 'move',      icon: '✥', label: 'Move',       key: 'W' },
  { id: 'rotate',    icon: '↺', label: 'Rotate',     key: 'E' },
  { id: 'scale',     icon: '⤢', label: 'Scale',      key: 'R' },
]

const viewModes = [
  { id: '3d',      label: '3D View' },
  { id: 'uv',      label: 'UV Editor' },
  { id: 'texture', label: 'Texture Paint' },
]

export default function Toolbar() {
  const { toggleLeftPanel, toggleRightPanel, toggleChatPanel, toggleSettings,
          leftPanelOpen, rightPanelOpen, chatPanelOpen } = useUIStore()
  const { viewportMode, setViewportMode } = useSceneStore()
  const { aiApiKey } = useSettingsStore()

  const [activeTool, setActiveTool] = React.useState('select')

  return (
    <div
      className="flex items-center gap-1 px-2 flex-shrink-0"
      style={{
        height: 'var(--toolbar-h)',
        background: 'var(--gf-bg-1)',
        borderBottom: '1px solid var(--gf-border)',
        zIndex: 50,
      }}
    >
      {/* Panel toggles */}
      <div className="flex items-center gap-1 pr-2" style={{ borderRight: '1px solid var(--gf-border)' }}>
        <TbBtn active={leftPanelOpen}  onClick={toggleLeftPanel}  title="Scene Panel">
          <PanelLeftIcon />
        </TbBtn>
      </div>

      {/* Transform tools */}
      <div className="flex items-center gap-1 px-2" style={{ borderRight: '1px solid var(--gf-border)' }}>
        {tools.map(t => (
          <TbBtn key={t.id} active={activeTool === t.id}
                 onClick={() => setActiveTool(t.id)}
                 title={`${t.label} (${t.key})`}>
            <span style={{ fontSize: 14 }}>{t.icon}</span>
          </TbBtn>
        ))}
      </div>

      {/* Viewport mode switcher */}
      <div className="flex items-center gap-1 px-2" style={{ borderRight: '1px solid var(--gf-border)' }}>
        {viewModes.map(m => (
          <button key={m.id}
            onClick={() => setViewportMode(m.id)}
            style={{
              height: 28, padding: '0 10px',
              background: viewportMode === m.id ? 'var(--gf-bg-3)' : 'transparent',
              border: viewportMode === m.id ? '1px solid var(--gf-border-h)' : '1px solid transparent',
              borderRadius: 'var(--gf-radius-sm)',
              color: viewportMode === m.id ? 'var(--gf-text)' : 'var(--gf-text-3)',
              fontSize: 12, fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Right side */}
      <div className="flex items-center gap-1 pl-2" style={{ borderLeft: '1px solid var(--gf-border)' }}>
        {/* AI status indicator */}
        <div
          title={aiApiKey ? 'AI connected' : 'No API key — click Settings'}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            padding: '0 8px', height: 28,
            background: 'var(--gf-bg-3)',
            border: `1px solid ${aiApiKey ? 'var(--gf-success)' : 'var(--gf-border)'}`,
            borderRadius: 'var(--gf-radius-sm)',
            fontSize: 11,
            color: aiApiKey ? 'var(--gf-success)' : 'var(--gf-text-3)',
            cursor: 'pointer',
          }}
          onClick={toggleSettings}
        >
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: aiApiKey ? 'var(--gf-success)' : 'var(--gf-text-3)',
            flexShrink: 0,
          }}/>
          {aiApiKey ? 'AI Ready' : 'AI Offline'}
        </div>

        <TbBtn active={chatPanelOpen}    onClick={toggleChatPanel}  title="AI Chat">
          <ChatIcon />
        </TbBtn>
        <TbBtn active={rightPanelOpen}   onClick={toggleRightPanel} title="Properties Panel">
          <PanelRightIcon />
        </TbBtn>
        <TbBtn onClick={toggleSettings} title="Settings">
          <GearIcon />
        </TbBtn>
      </div>
    </div>
  )
}

function TbBtn({ children, onClick, active, title }) {
  return (
    <button onClick={onClick} title={title} style={{
      width: 30, height: 30,
      background: active ? 'var(--gf-bg-3)' : 'transparent',
      border: active ? '1px solid var(--gf-border-h)' : '1px solid transparent',
      borderRadius: 'var(--gf-radius-sm)',
      color: active ? 'var(--gf-text)' : 'var(--gf-text-3)',
      cursor: 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      transition: 'all 0.15s',
      flexShrink: 0,
    }}
    onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--gf-bg-3)'; e.currentTarget.style.color = 'var(--gf-text)' }}}
    onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--gf-text-3)' }}}
    >
      {children}
    </button>
  )
}

// Icons
const PanelLeftIcon  = () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="1" y="1" width="14" height="14" rx="2"/><line x1="5" y1="1" x2="5" y2="15"/></svg>
const PanelRightIcon = () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="1" y="1" width="14" height="14" rx="2"/><line x1="11" y1="1" x2="11" y2="15"/></svg>
const ChatIcon       = () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 10a2 2 0 0 1-2 2H4l-3 3V3a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2z"/></svg>
const GearIcon       = () => <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="2.5"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41"/></svg>
