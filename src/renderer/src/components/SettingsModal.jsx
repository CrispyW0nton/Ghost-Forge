import React, { useState } from 'react'
import { useSettingsStore, useUIStore } from '../store'

const PROVIDERS = [
  { id: 'openai',    label: 'OpenAI',     placeholder: 'sk-…',          defaultUrl: 'https://api.openai.com/v1',       models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'] },
  { id: 'anthropic', label: 'Anthropic',  placeholder: 'sk-ant-…',      defaultUrl: 'https://api.anthropic.com/v1',    models: ['claude-3-5-sonnet-20241022', 'claude-3-haiku-20240307'] },
  { id: 'ollama',    label: 'Ollama (local)', placeholder: '(not needed)', defaultUrl: 'http://localhost:11434/v1',     models: ['llama3.2', 'mistral', 'codellama', 'phi3'] },
  { id: 'custom',    label: 'Custom / Other', placeholder: 'your-api-key', defaultUrl: 'https://your-api.com/v1',    models: [] },
]

export default function SettingsModal() {
  const { toggleSettings } = useUIStore()
  const {
    aiApiKey, aiModel, aiBaseUrl, aiProvider,
    setAiApiKey, setAiModel, setAiBaseUrl, setAiProvider,
    viewportGrid, viewportWireframe, viewportShadows,
    toggleGrid, toggleWireframe,
    defaultTextureSize, defaultPadding,
  } = useSettingsStore()

  const [tab, setTab]     = useState('ai')
  const [showKey, setShowKey] = useState(false)
  const [localKey, setLocalKey]     = useState(aiApiKey)
  const [localModel, setLocalModel] = useState(aiModel)
  const [localUrl, setLocalUrl]     = useState(aiBaseUrl)
  const [saved, setSaved] = useState(false)

  const provider = PROVIDERS.find(p => p.id === aiProvider) || PROVIDERS[0]

  const handleProviderChange = (pid) => {
    setAiProvider(pid)
    const p = PROVIDERS.find(x => x.id === pid)
    setLocalUrl(p.defaultUrl)
    setLocalModel(p.models[0] || '')
  }

  const handleSave = () => {
    setAiApiKey(localKey)
    setAiModel(localModel)
    setAiBaseUrl(localUrl)
    setSaved(true)
    setTimeout(() => { setSaved(false); toggleSettings() }, 800)
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      backdropFilter: 'blur(4px)',
    }}
    onClick={e => { if (e.target === e.currentTarget) toggleSettings() }}
    >
      <div style={{
        width: 560, maxHeight: '80vh',
        background: 'var(--gf-bg-2)',
        border: '1px solid var(--gf-border-h)',
        borderRadius: 'var(--gf-radius-lg)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
        animation: 'fadeIn 0.2s ease',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid var(--gf-border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 18 }}>⚙️</span>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--gf-text)' }}>Settings</div>
              <div style={{ fontSize: 11, color: 'var(--gf-text-3)' }}>GhostForge v0.1.0</div>
            </div>
          </div>
          <button onClick={toggleSettings} style={{
            background: 'none', border: 'none', color: 'var(--gf-text-3)',
            fontSize: 20, cursor: 'pointer', width: 28, height: 28,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            borderRadius: 4, transition: 'all 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--gf-bg-3)'; e.currentTarget.style.color = 'var(--gf-text)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--gf-text-3)' }}
          >×</button>
        </div>

        {/* Tab bar */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--gf-border)', flexShrink: 0 }}>
          {['ai', 'viewport', 'about'].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              flex: 1, height: 36,
              background: tab === t ? 'var(--gf-bg-3)' : 'transparent',
              border: 'none',
              borderBottom: tab === t ? '2px solid var(--gf-forge)' : '2px solid transparent',
              color: tab === t ? 'var(--gf-text)' : 'var(--gf-text-3)',
              fontSize: 12, fontWeight: 600, cursor: 'pointer', textTransform: 'capitalize',
              transition: 'all 0.15s',
            }}>{t === 'ai' ? '🤖 AI' : t === 'viewport' ? '🖥 Viewport' : 'ℹ About'}</button>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>

          {/* ─── AI Settings ─── */}
          {tab === 'ai' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{
                background: 'rgba(255,107,43,0.08)', border: '1px solid rgba(255,107,43,0.2)',
                borderRadius: 'var(--gf-radius)', padding: 12, fontSize: 12,
                color: 'var(--gf-text-2)', lineHeight: 1.7,
              }}>
                🔑 Enter your API key to enable AI assistance. Your key is stored locally and never sent anywhere except directly to your chosen AI provider.
              </div>

              {/* Provider selector */}
              <SettingGroup label="AI Provider">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                  {PROVIDERS.map(p => (
                    <button key={p.id} onClick={() => handleProviderChange(p.id)} style={{
                      padding: '8px 12px', textAlign: 'left',
                      background: aiProvider === p.id ? 'rgba(255,107,43,0.1)' : 'var(--gf-bg-3)',
                      border: `1px solid ${aiProvider === p.id ? 'var(--gf-forge)' : 'var(--gf-border)'}`,
                      borderRadius: 'var(--gf-radius-sm)',
                      color: aiProvider === p.id ? 'var(--gf-text)' : 'var(--gf-text-2)',
                      fontSize: 12, cursor: 'pointer', transition: 'all 0.15s',
                    }}>
                      {p.label}
                    </button>
                  ))}
                </div>
              </SettingGroup>

              {/* API Key */}
              <SettingGroup label="API Key">
                <div style={{ position: 'relative' }}>
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={localKey}
                    onChange={e => setLocalKey(e.target.value)}
                    placeholder={provider.placeholder}
                    style={inputStyle}
                  />
                  <button onClick={() => setShowKey(!showKey)} style={{
                    position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', color: 'var(--gf-text-3)',
                    cursor: 'pointer', fontSize: 11,
                  }}>{showKey ? 'Hide' : 'Show'}</button>
                </div>
              </SettingGroup>

              {/* Model */}
              <SettingGroup label="Model">
                {provider.models.length > 0 ? (
                  <select value={localModel} onChange={e => setLocalModel(e.target.value)} style={inputStyle}>
                    {provider.models.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                ) : (
                  <input type="text" value={localModel} onChange={e => setLocalModel(e.target.value)}
                         placeholder="e.g. gpt-4o, claude-3-5-sonnet, llama3.2"
                         style={inputStyle} />
                )}
              </SettingGroup>

              {/* Base URL */}
              <SettingGroup label="API Base URL">
                <input type="text" value={localUrl} onChange={e => setLocalUrl(e.target.value)}
                       placeholder="https://api.openai.com/v1" style={inputStyle} />
                <p style={{ fontSize: 10, color: 'var(--gf-text-3)', marginTop: 4 }}>
                  Any OpenAI-compatible endpoint works (Ollama, LM Studio, Together AI, etc.)
                </p>
              </SettingGroup>
            </div>
          )}

          {/* ─── Viewport Settings ─── */}
          {tab === 'viewport' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <ToggleRow label="Show Grid"      value={viewportGrid}      onChange={toggleGrid} />
              <ToggleRow label="Wireframe Mode" value={viewportWireframe} onChange={toggleWireframe} />
            </div>
          )}

          {/* ─── About ─── */}
          {tab === 'about' && (
            <div style={{ textAlign: 'center', padding: '10px 0' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>👻🔥</div>
              <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>
                <span style={{ color: 'var(--gf-ghost)' }}>Ghost</span>
                <span style={{ color: 'var(--gf-forge)' }}>Forge</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--gf-text-3)', marginBottom: 16 }}>
                v0.1.0 — Open source 3D creation suite
              </div>
              <div style={{
                background: 'var(--gf-bg-3)', border: '1px solid var(--gf-border)',
                borderRadius: 'var(--gf-radius)', padding: 14,
                fontSize: 11, color: 'var(--gf-text-2)', lineHeight: 1.8,
                textAlign: 'left',
              }}>
                <div style={{ marginBottom: 8, fontWeight: 600, color: 'var(--gf-text)' }}>Open Source Stack</div>
                <div>🔷 <strong>xatlas</strong> — UV unwrapping (ABF++)</div>
                <div>🔷 <strong>trimesh</strong> — Mesh processing</div>
                <div>🔷 <strong>Stable Diffusion</strong> — AI texturing</div>
                <div>🔷 <strong>Three.js / R3F</strong> — 3D viewport</div>
                <div>🔷 <strong>Electron + React</strong> — Desktop app</div>
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--gf-border)',
                              color: 'var(--gf-text-3)', fontSize: 10 }}>
                  Based on <a href="https://github.com/lightningpixel/modly" target="_blank"
                    style={{ color: 'var(--gf-ghost)' }}>Modly</a> by Lightning Pixel (MIT License)
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {tab === 'ai' && (
          <div style={{
            padding: '12px 20px', borderTop: '1px solid var(--gf-border)',
            display: 'flex', gap: 8, justifyContent: 'flex-end', flexShrink: 0,
          }}>
            <button onClick={toggleSettings} style={{
              padding: '8px 16px', background: 'transparent',
              border: '1px solid var(--gf-border)', borderRadius: 6,
              color: 'var(--gf-text-2)', fontSize: 13, cursor: 'pointer',
            }}>Cancel</button>
            <button onClick={handleSave} style={{
              padding: '8px 20px',
              background: saved ? 'var(--gf-success)' : 'var(--gf-forge)',
              border: 'none', borderRadius: 6,
              color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              transition: 'background 0.2s',
            }}>
              {saved ? '✓ Saved!' : 'Save Settings'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function SettingGroup({ label, children }) {
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--gf-text-2)', marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  )
}

function ToggleRow({ label, value, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '8px 0', borderBottom: '1px solid var(--gf-border)' }}>
      <span style={{ fontSize: 13, color: 'var(--gf-text-2)' }}>{label}</span>
      <div onClick={onChange} style={{
        width: 40, height: 22, borderRadius: 11,
        background: value ? 'var(--gf-forge)' : 'var(--gf-bg-3)',
        border: `1px solid ${value ? 'var(--gf-forge)' : 'var(--gf-border)'}`,
        cursor: 'pointer', position: 'relative', transition: 'all 0.2s',
      }}>
        <div style={{
          position: 'absolute', top: 3, left: value ? 20 : 3,
          width: 14, height: 14, borderRadius: '50%',
          background: value ? '#fff' : 'var(--gf-text-3)',
          transition: 'left 0.2s',
        }}/>
      </div>
    </div>
  )
}

const inputStyle = {
  width: '100%', background: 'var(--gf-bg-3)',
  border: '1px solid var(--gf-border)', borderRadius: 'var(--gf-radius-sm)',
  color: 'var(--gf-text)', fontSize: 13, padding: '8px 10px',
  fontFamily: 'inherit', outline: 'none',
  userSelect: 'text',
}
