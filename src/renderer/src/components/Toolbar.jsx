import React, { useState } from 'react'
import { useUIStore, useSceneStore, useSettingsStore } from '../store'

const tools = [
  { id: 'select', label: 'Select', key: 'Q',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.3"><path d="M2 2 L2 10 L5 8 L6.5 11 L8 10.5 L6.5 7.5 L9.5 7.5 Z"/></svg> },
  { id: 'move',   label: 'Move',   key: 'W',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.3"><path d="M6.5 1.5v10M1.5 6.5h10M6.5 1.5L5 3M6.5 1.5L8 3M6.5 11.5L5 10M6.5 11.5L8 10M1.5 6.5L3 5M1.5 6.5L3 8M11.5 6.5L10 5M11.5 6.5L10 8"/></svg> },
  { id: 'rotate', label: 'Rotate', key: 'E',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.3"><path d="M10.5 6.5A4 4 0 1 1 8 3"/><path d="M8 1v2.5L10.5 3"/></svg> },
  { id: 'scale',  label: 'Scale',  key: 'R',
    icon: <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.3"><path d="M2 11L11 2M9 2h2v2M2 9v2h2"/></svg> },
]

const viewModes = [
  { id: '3d',      label: '3D_VIEW' },
  { id: 'uv',      label: 'UV_EDIT' },
  { id: 'texture', label: 'TEX_PAINT' },
]

export default function Toolbar() {
  const { toggleLeftPanel, toggleRightPanel, toggleChatPanel, toggleSettings,
          leftPanelOpen, rightPanelOpen, chatPanelOpen } = useUIStore()
  const { viewportMode, setViewportMode } = useSceneStore()
  const { aiApiKey, aiModel } = useSettingsStore()
  const [activeTool, setActiveTool] = useState('select')

  return (
    <div
      className="flex items-center gap-1 flex-shrink-0"
      style={{
        height: 'var(--toolbar-h)',
        background: 'var(--gf-bg-1)',
        borderBottom: '1px solid var(--gf-border)',
        boxShadow: '0 1px 0 #39FF1410',
        padding: '0 8px',
        zIndex: 50,
      }}
    >
      {/* Panel toggle — left */}
      <div className="flex items-center" style={{ paddingRight: 8, borderRight: '1px solid var(--gf-border)', marginRight: 4 }}>
        <TbBtn active={leftPanelOpen} onClick={toggleLeftPanel} title="Scene Panel [Scene]">
          <PanelLeftIcon />
        </TbBtn>
      </div>

      {/* Transform tools */}
      <div className="flex items-center gap-1" style={{ paddingRight: 8, borderRight: '1px solid var(--gf-border)', marginRight: 4 }}>
        {tools.map(t => (
          <TbBtn key={t.id}
            active={activeTool === t.id}
            onClick={() => setActiveTool(t.id)}
            title={`${t.label}  [${t.key}]`}
          >
            {t.icon}
          </TbBtn>
        ))}
      </div>

      {/* Viewport mode switcher */}
      <div className="flex items-center gap-1" style={{ paddingRight: 8, borderRight: '1px solid var(--gf-border)', marginRight: 4 }}>
        {viewModes.map(m => (
          <button key={m.id}
            onClick={() => setViewportMode(m.id)}
            style={{
              height: 26, padding: '0 9px',
              background: viewportMode === m.id ? 'var(--gf-bg-4)' : 'transparent',
              border: viewportMode === m.id
                ? '1px solid var(--gf-neon-dim)'
                : '1px solid transparent',
              borderRadius: 'var(--gf-radius-sm)',
              color: viewportMode === m.id ? 'var(--gf-neon)' : 'var(--gf-text-3)',
              fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
              cursor: 'pointer', transition: 'all 0.12s',
              fontFamily: 'monospace',
              boxShadow: viewportMode === m.id ? '0 0 6px #39FF1433' : 'none',
              textShadow: viewportMode === m.id ? '0 0 6px var(--gf-neon)' : 'none',
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Right side controls */}
      <div className="flex items-center gap-1" style={{ paddingLeft: 8, borderLeft: '1px solid var(--gf-border)' }}>

        {/* AI status pill */}
        <div
          onClick={toggleSettings}
          title={aiApiKey ? `AI: ${aiModel}` : 'Configure AI — click to open settings'}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            padding: '0 8px', height: 24,
            background: aiApiKey ? 'rgba(57,255,20,0.06)' : 'var(--gf-bg-3)',
            border: `1px solid ${aiApiKey ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
            borderRadius: 'var(--gf-radius-sm)',
            fontSize: 9, letterSpacing: '0.1em', fontFamily: 'monospace',
            color: aiApiKey ? 'var(--gf-neon)' : 'var(--gf-text-3)',
            cursor: 'pointer', transition: 'all 0.12s',
            textTransform: 'uppercase',
            boxShadow: aiApiKey ? '0 0 8px #39FF1420' : 'none',
          }}
        >
          <span style={{
            width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
            background: aiApiKey ? 'var(--gf-neon)' : 'var(--gf-text-3)',
            boxShadow: aiApiKey ? '0 0 5px var(--gf-neon)' : 'none',
            animation: aiApiKey ? 'pulse 2s ease infinite' : 'none',
          }}/>
          {aiApiKey ? 'AI_ONLINE' : 'AI_OFFLINE'}
        </div>

        <TbBtn active={chatPanelOpen}  onClick={toggleChatPanel}  title="AI Chat">
          <ChatIcon />
        </TbBtn>
        <TbBtn active={rightPanelOpen} onClick={toggleRightPanel} title="Properties">
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
  const [hover, setHover] = useState(false)
  const on = active || hover
  return (
    <button
      onClick={onClick}
      title={title}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: 28, height: 28,
        background: active ? 'var(--gf-bg-4)' : hover ? 'var(--gf-bg-3)' : 'transparent',
        border: `1px solid ${on ? 'var(--gf-border-h)' : 'transparent'}`,
        borderRadius: 'var(--gf-radius-sm)',
        color: on ? 'var(--gf-neon)' : 'var(--gf-text-3)',
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.12s', flexShrink: 0,
        boxShadow: active ? '0 0 6px #39FF1425' : 'none',
        filter: on ? 'drop-shadow(0 0 2px var(--gf-neon-dim))' : 'none',
      }}
    >
      {children}
    </button>
  )
}

// Icons
const PanelLeftIcon  = () => <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.2"><rect x="1" y="1" width="12" height="12" rx="1.5"/><line x1="4.5" y1="1" x2="4.5" y2="13"/></svg>
const PanelRightIcon = () => <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.2"><rect x="1" y="1" width="12" height="12" rx="1.5"/><line x1="9.5" y1="1" x2="9.5" y2="13"/></svg>
const ChatIcon       = () => <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.2"><path d="M12 9a1.5 1.5 0 0 1-1.5 1.5H4L1.5 13V3A1.5 1.5 0 0 1 3 1.5h7.5A1.5 1.5 0 0 1 12 3Z"/></svg>
const GearIcon       = () => <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.2"><circle cx="7" cy="7" r="2"/><path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.93 2.93l1.06 1.06M10.01 10.01l1.06 1.06M2.93 11.07l1.06-1.06M10.01 3.99l1.06-1.06"/></svg>
