import React, { useState } from 'react'
import { useSettingsStore, useUIStore } from '../store'
import MatrixRain from './MatrixRain'

const PROVIDERS = [
  {
    id: 'openai', label: 'OpenAI', placeholder: 'sk-…',
    defaultUrl: 'https://api.openai.com/v1',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    desc: 'GPT-4o, fastest general AI',
  },
  {
    id: 'anthropic', label: 'Anthropic', placeholder: 'sk-ant-…',
    defaultUrl: 'https://api.anthropic.com/v1',
    models: ['claude-3-5-sonnet-20241022', 'claude-3-haiku-20240307'],
    desc: 'Claude 3.5, best for code',
  },
  {
    id: 'ollama', label: 'Ollama (local)', placeholder: '(not needed)',
    defaultUrl: 'http://localhost:11434/v1',
    models: ['llama3.2', 'mistral', 'codellama', 'phi3'],
    desc: 'Fully offline, local models',
  },
  {
    id: 'custom', label: 'Custom / Other', placeholder: 'your-api-key',
    defaultUrl: 'https://your-api.com/v1',
    models: [],
    desc: 'Any OpenAI-compatible API',
  },
]

export default function SettingsModal() {
  const { toggleSettings } = useUIStore()
  const {
    aiApiKey, aiModel, aiBaseUrl, aiProvider,
    setAiApiKey, setAiModel, setAiBaseUrl, setAiProvider,
    viewportGrid, viewportWireframe,
    toggleGrid, toggleWireframe,
  } = useSettingsStore()

  const [tab, setTab]           = useState('ai')
  const [showKey, setShowKey]   = useState(false)
  const [localKey, setLocalKey] = useState(aiApiKey)
  const [localModel, setLocalModel] = useState(aiModel)
  const [localUrl, setLocalUrl] = useState(aiBaseUrl)
  const [saved, setSaved]       = useState(false)

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
    setTimeout(() => { setSaved(false); toggleSettings() }, 900)
  }

  const tabs = [
    { id: 'ai',       label: '> AI_NEURAL' },
    { id: 'viewport', label: '> VIEWPORT' },
    { id: 'about',    label: '> ABOUT' },
  ]

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0, 0, 0, 0.82)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      backdropFilter: 'blur(6px)',
    }}
    onClick={e => { if (e.target === e.currentTarget) toggleSettings() }}
    >
      <div style={{
        width: 580, maxHeight: '85vh',
        background: 'var(--gf-bg-2)',
        border: '1px solid var(--gf-neon-dim)',
        borderRadius: 'var(--gf-radius-lg)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 0 40px #39FF1420, 0 20px 60px rgba(0,0,0,0.8)',
        animation: 'fadeIn 0.18s ease',
        position: 'relative',
      }}>
        {/* Subtle Matrix rain in backdrop */}
        <div style={{ position: 'absolute', inset: 0, zIndex: 0, overflow: 'hidden', borderRadius: 'inherit' }}>
          <MatrixRain opacity={0.025} fontSize={11} speed={0.5} />
        </div>

        {/* Content above rain */}
        <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>

          {/* ── Header ── */}
          <div style={{
            padding: '14px 18px',
            borderBottom: '1px solid var(--gf-border)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            flexShrink: 0,
            background: 'var(--gf-bg-1)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              {/* Ghost icon */}
              <div style={{
                width: 34, height: 34,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: '1px solid var(--gf-neon-dim)',
                borderRadius: 4,
                background: 'rgba(57,255,20,0.06)',
                boxShadow: '0 0 8px #39FF1430',
              }}>
                <svg width="18" height="18" viewBox="0 0 32 32" fill="none">
                  <path d="M4 30 L4 16 C4 8 9 3 16 3 C23 3 28 8 28 16 L28 30 L24 27 L20 30 L16 27 L12 30 L8 27 Z"
                        fill="#050D05" stroke="#39FF14" strokeWidth="0.8"/>
                  <path d="M7 28 L7 17 C7 11 11 6 16 6 C21 6 25 11 25 17 L25 28 L22 26 L16 28 L10 26 Z"
                        fill="#020402"/>
                  <ellipse cx="12.5" cy="17" rx="2.2" ry="1.6" fill="#39FF14"
                    style={{ filter: 'drop-shadow(0 0 4px #39FF14)' }}/>
                  <ellipse cx="19.5" cy="17" rx="2.2" ry="1.6" fill="#39FF14"
                    style={{ filter: 'drop-shadow(0 0 4px #39FF14)' }}/>
                </svg>
              </div>
              <div>
                <div style={{
                  fontSize: 14, fontWeight: 700,
                  color: 'var(--gf-neon)',
                  fontFamily: 'monospace', letterSpacing: '0.08em',
                  textShadow: '0 0 8px var(--gf-neon)',
                  textTransform: 'uppercase',
                }}>
                  GhostForge<span style={{ color: 'var(--gf-text-3)' }}>::</span>SETTINGS
                </div>
                <div style={{
                  fontSize: 9, color: 'var(--gf-text-3)',
                  fontFamily: 'monospace', letterSpacing: '0.12em',
                }}>
                  v0.1.0 // SYSTEM_CONFIGURATION
                </div>
              </div>
            </div>

            <button onClick={toggleSettings} style={{
              width: 28, height: 28,
              background: 'transparent',
              border: '1px solid var(--gf-border-h)',
              borderRadius: 'var(--gf-radius-sm)',
              color: 'var(--gf-text-3)',
              fontSize: 16, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: 'monospace', transition: 'all 0.1s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--gf-danger)'
              e.currentTarget.style.color = 'var(--gf-danger)'
              e.currentTarget.style.boxShadow = '0 0 6px #FF2D5544'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--gf-border-h)'
              e.currentTarget.style.color = 'var(--gf-text-3)'
              e.currentTarget.style.boxShadow = 'none'
            }}
            >×</button>
          </div>

          {/* ── Tab bar ── */}
          <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--gf-border)',
            flexShrink: 0,
            background: 'var(--gf-bg-1)',
          }}>
            {tabs.map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                flex: 1, height: 36,
                background: tab === t.id ? 'var(--gf-bg-3)' : 'transparent',
                border: 'none',
                borderBottom: tab === t.id ? '2px solid var(--gf-neon)' : '2px solid transparent',
                color: tab === t.id ? 'var(--gf-neon)' : 'var(--gf-text-3)',
                fontSize: 9, fontWeight: 700, cursor: 'pointer',
                fontFamily: 'monospace', letterSpacing: '0.1em',
                textTransform: 'uppercase', transition: 'all 0.1s',
                textShadow: tab === t.id ? '0 0 6px var(--gf-neon)' : 'none',
              }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* ── Content ── */}
          <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>

            {/* ─── AI Settings ─── */}
            {tab === 'ai' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

                {/* Info banner */}
                <div style={{
                  background: 'rgba(57,255,20,0.04)',
                  border: '1px solid rgba(57,255,20,0.2)',
                  borderRadius: 'var(--gf-radius-sm)',
                  padding: '10px 12px',
                  fontSize: 10, color: 'var(--gf-text-2)',
                  lineHeight: 1.7, fontFamily: 'monospace',
                }}>
                  <span style={{ color: 'var(--gf-neon-dim)' }}>&gt; </span>
                  API key stored locally — never leaves your machine.<br/>
                  <span style={{ color: 'var(--gf-neon-dim)' }}>&gt; </span>
                  Sent only to your chosen provider endpoint.
                </div>

                {/* Provider selector */}
                <SettingGroup label="AI_PROVIDER">
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                    {PROVIDERS.map(p => (
                      <button key={p.id} onClick={() => handleProviderChange(p.id)} style={{
                        padding: '8px 12px', textAlign: 'left',
                        background: aiProvider === p.id ? 'rgba(57,255,20,0.08)' : 'var(--gf-bg-3)',
                        border: `1px solid ${aiProvider === p.id ? 'var(--gf-neon-dim)' : 'var(--gf-border-h)'}`,
                        borderRadius: 'var(--gf-radius-sm)',
                        cursor: 'pointer', transition: 'all 0.1s',
                        boxShadow: aiProvider === p.id ? '0 0 8px #39FF1430' : 'none',
                      }}>
                        <div style={{
                          fontSize: 10, fontWeight: 700, fontFamily: 'monospace',
                          color: aiProvider === p.id ? 'var(--gf-neon)' : 'var(--gf-text-2)',
                          letterSpacing: '0.08em', textTransform: 'uppercase',
                          textShadow: aiProvider === p.id ? '0 0 5px var(--gf-neon)' : 'none',
                          marginBottom: 2,
                        }}>
                          {aiProvider === p.id ? '> ' : '  '}{p.label}
                        </div>
                        <div style={{
                          fontSize: 9, color: 'var(--gf-text-3)',
                          fontFamily: 'monospace',
                        }}>{p.desc}</div>
                      </button>
                    ))}
                  </div>
                </SettingGroup>

                {/* API Key */}
                <SettingGroup label="API_KEY">
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showKey ? 'text' : 'password'}
                      value={localKey}
                      onChange={e => setLocalKey(e.target.value)}
                      placeholder={provider.placeholder}
                      style={{ ...matrixInput, paddingRight: 56 }}
                    />
                    <button onClick={() => setShowKey(!showKey)} style={{
                      position: 'absolute', right: 8, top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'none', border: 'none',
                      color: 'var(--gf-text-3)',
                      cursor: 'pointer', fontSize: 9,
                      fontFamily: 'monospace', letterSpacing: '0.08em',
                    }}>
                      {showKey ? 'HIDE' : 'SHOW'}
                    </button>
                  </div>
                </SettingGroup>

                {/* Model */}
                <SettingGroup label="AI_MODEL">
                  {provider.models.length > 0 ? (
                    <select
                      value={localModel}
                      onChange={e => setLocalModel(e.target.value)}
                      style={matrixInput}
                    >
                      {provider.models.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={localModel}
                      onChange={e => setLocalModel(e.target.value)}
                      placeholder="gpt-4o, claude-3-5-sonnet, llama3.2…"
                      style={matrixInput}
                    />
                  )}
                </SettingGroup>

                {/* Base URL */}
                <SettingGroup label="API_BASE_URL">
                  <input
                    type="text"
                    value={localUrl}
                    onChange={e => setLocalUrl(e.target.value)}
                    placeholder="https://api.openai.com/v1"
                    style={matrixInput}
                  />
                  <p style={{
                    fontSize: 9, color: 'var(--gf-text-3)',
                    marginTop: 5, fontFamily: 'monospace',
                    letterSpacing: '0.05em',
                  }}>
                    // Any OpenAI-compatible endpoint (Ollama, LM Studio, Together AI…)
                  </p>
                </SettingGroup>
              </div>
            )}

            {/* ─── Viewport Settings ─── */}
            {tab === 'viewport' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <MatrixToggleRow label="SHOW_GRID"      value={viewportGrid}      onChange={toggleGrid} />
                <MatrixToggleRow label="WIREFRAME_MODE" value={viewportWireframe} onChange={toggleWireframe} />

                <div style={{
                  marginTop: 12, padding: '10px 12px',
                  background: 'rgba(0,229,255,0.04)',
                  border: '1px solid rgba(0,229,255,0.15)',
                  borderRadius: 'var(--gf-radius-sm)',
                  fontSize: 9, color: 'var(--gf-cyan-dim)',
                  fontFamily: 'monospace', lineHeight: 1.8,
                }}>
                  // Grid uses neon green (#39FF14) for main lines<br/>
                  // Sub-grid uses dark green (#0D2A0D)<br/>
                  // Axis: X=red, Y=neon-green, Z=cyan
                </div>
              </div>
            )}

            {/* ─── About ─── */}
            {tab === 'about' && (
              <div>
                {/* Logo section */}
                <div style={{ textAlign: 'center', marginBottom: 24 }}>
                  <div className="animate-eye-glow" style={{ display: 'inline-block', marginBottom: 10 }}>
                    <svg width="56" height="56" viewBox="0 0 32 32" fill="none">
                      <path d="M4 30 L4 16 C4 8 9 3 16 3 C23 3 28 8 28 16 L28 30 L24 27 L20 30 L16 27 L12 30 L8 27 Z"
                            fill="#050D05" stroke="#39FF14" strokeWidth="0.8"/>
                      <path d="M7 28 L7 17 C7 11 11 6 16 6 C21 6 25 11 25 17 L25 28 L22 26 L16 28 L10 26 Z"
                            fill="#020402"/>
                      <ellipse cx="12.5" cy="17" rx="2.8" ry="2" fill="#39FF14"
                        style={{ filter: 'drop-shadow(0 0 6px #39FF14) drop-shadow(0 0 12px #2CFF2C)' }}/>
                      <ellipse cx="19.5" cy="17" rx="2.8" ry="2" fill="#39FF14"
                        style={{ filter: 'drop-shadow(0 0 6px #39FF14) drop-shadow(0 0 12px #2CFF2C)' }}/>
                      <ellipse cx="12.5" cy="17" rx="1.2" ry="0.9" fill="#E0FFE0" opacity="0.9"/>
                      <ellipse cx="19.5" cy="17" rx="1.2" ry="0.9" fill="#E0FFE0" opacity="0.9"/>
                    </svg>
                  </div>

                  <div style={{
                    fontSize: 22, fontWeight: 700, fontFamily: 'monospace',
                    letterSpacing: '0.08em', marginBottom: 4,
                  }}>
                    <span style={{ color: 'var(--gf-neon)', textShadow: '0 0 12px var(--gf-neon)' }}>Ghost</span>
                    <span style={{ color: 'var(--gf-neon-bright)', textShadow: '0 0 12px var(--gf-neon-bright)' }}>Forge</span>
                  </div>
                  <div style={{
                    fontSize: 9, color: 'var(--gf-text-3)',
                    fontFamily: 'monospace', letterSpacing: '0.15em',
                    textTransform: 'uppercase',
                  }}>
                    v0.1.0 // Open Source 3D Creation Suite
                  </div>
                </div>

                {/* Tech stack */}
                <div style={{
                  background: 'var(--gf-bg-3)',
                  border: '1px solid var(--gf-border)',
                  borderRadius: 'var(--gf-radius)',
                  padding: 14, fontSize: 10,
                  color: 'var(--gf-text-2)', lineHeight: 2,
                  fontFamily: 'monospace',
                }}>
                  <div style={{
                    marginBottom: 8, fontWeight: 700,
                    color: 'var(--gf-neon)', letterSpacing: '0.1em',
                    textShadow: '0 0 6px var(--gf-neon)',
                    fontSize: 9, textTransform: 'uppercase',
                  }}>
                    // OPEN_SOURCE_STACK
                  </div>
                  {[
                    ['xatlas',              'UV unwrapping — ABF++ algorithm',         'var(--gf-neon)'],
                    ['trimesh',             'Mesh processing pipeline',                 'var(--gf-neon-dim)'],
                    ['Stable Diffusion',    'AI texture generation',                    'var(--gf-cyan)'],
                    ['Three.js / R3F',      '3D viewport rendering',                   'var(--gf-cyan-dim)'],
                    ['Electron + React',    'Desktop application framework',           'var(--gf-neon)'],
                    ['Flask',               'Python backend REST API',                  'var(--gf-neon-dim)'],
                    ['Zustand',             'State management',                        'var(--gf-text-2)'],
                  ].map(([name, desc, col]) => (
                    <div key={name} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                      <span style={{ color: col, fontWeight: 700, minWidth: 130, textShadow: `0 0 4px ${col}` }}>&gt; {name}</span>
                      <span style={{ color: 'var(--gf-text-3)', fontSize: 9 }}>// {desc}</span>
                    </div>
                  ))}

                  <div style={{
                    marginTop: 10, paddingTop: 10,
                    borderTop: '1px solid var(--gf-border)',
                    fontSize: 9, color: 'var(--gf-text-3)',
                  }}>
                    // Based on{' '}
                    <a href="https://github.com/lightningpixel/modly" target="_blank"
                       style={{ color: 'var(--gf-neon-dim)', textDecoration: 'none' }}>
                      Modly
                    </a>
                    {' '}by Lightning Pixel (MIT License)
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ── Footer (AI tab only) ── */}
          {tab === 'ai' && (
            <div style={{
              padding: '12px 18px',
              borderTop: '1px solid var(--gf-border)',
              display: 'flex', gap: 8, justifyContent: 'flex-end',
              flexShrink: 0, background: 'var(--gf-bg-1)',
            }}>
              <button onClick={toggleSettings} style={{
                padding: '7px 16px',
                background: 'transparent',
                border: '1px solid var(--gf-border-h)',
                borderRadius: 'var(--gf-radius-sm)',
                color: 'var(--gf-text-2)', fontSize: 10,
                fontFamily: 'monospace', letterSpacing: '0.08em',
                cursor: 'pointer', transition: 'all 0.1s',
                textTransform: 'uppercase',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gf-border-h)'; e.currentTarget.style.color = 'var(--gf-text)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--gf-border)'; e.currentTarget.style.color = 'var(--gf-text-2)' }}
              >
                CANCEL
              </button>

              <button onClick={handleSave} style={{
                padding: '7px 20px',
                background: saved
                  ? 'rgba(57,255,20,0.2)'
                  : 'rgba(57,255,20,0.1)',
                border: `1px solid ${saved ? 'var(--gf-neon)' : 'var(--gf-neon-dim)'}`,
                borderRadius: 'var(--gf-radius-sm)',
                color: 'var(--gf-neon)',
                fontSize: 10, fontWeight: 700,
                fontFamily: 'monospace', letterSpacing: '0.1em',
                cursor: 'pointer', transition: 'all 0.15s',
                textTransform: 'uppercase',
                textShadow: '0 0 6px var(--gf-neon)',
                boxShadow: saved
                  ? '0 0 16px #39FF1440'
                  : '0 0 8px #39FF1420',
              }}>
                {saved ? '> SAVED ✓' : '> SAVE_SETTINGS'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Shared sub-components ────────────────────────────────────────────────────
function SettingGroup({ label, children }) {
  return (
    <div>
      <div style={{
        fontSize: 9, fontWeight: 700, color: 'var(--gf-text-3)',
        marginBottom: 6, fontFamily: 'monospace',
        letterSpacing: '0.14em', textTransform: 'uppercase',
        display: 'flex', alignItems: 'center', gap: 5,
      }}>
        <span style={{ color: 'var(--gf-neon-dim)' }}>//</span>
        {label}
      </div>
      {children}
    </div>
  )
}

function MatrixToggleRow({ label, value, onChange }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '10px 0', borderBottom: '1px solid var(--gf-border)',
    }}>
      <span style={{
        fontSize: 10, color: value ? 'var(--gf-text-2)' : 'var(--gf-text-3)',
        fontFamily: 'monospace', letterSpacing: '0.1em',
        textTransform: 'uppercase',
      }}>
        {value ? '> ' : '  '}{label}
      </span>

      <div onClick={onChange} style={{
        width: 38, height: 20, borderRadius: 10,
        background: value ? 'rgba(57,255,20,0.15)' : 'var(--gf-bg-3)',
        border: `1px solid ${value ? 'var(--gf-neon-dim)' : 'var(--gf-border-h)'}`,
        boxShadow: value ? '0 0 8px #39FF1430' : 'none',
        cursor: 'pointer', position: 'relative',
        transition: 'all 0.2s', flexShrink: 0,
      }}>
        <div style={{
          position: 'absolute', top: 2,
          left: value ? 19 : 2,
          width: 14, height: 14, borderRadius: '50%',
          background: value ? 'var(--gf-neon)' : 'var(--gf-text-3)',
          boxShadow: value ? '0 0 6px var(--gf-neon)' : 'none',
          transition: 'left 0.2s',
        }}/>
      </div>
    </div>
  )
}

const matrixInput = {
  width: '100%',
  background: 'var(--gf-bg-3)',
  border: '1px solid var(--gf-border-h)',
  borderRadius: 'var(--gf-radius-sm)',
  color: 'var(--gf-text)',
  fontSize: 11,
  padding: '8px 10px',
  fontFamily: "'Courier New', monospace",
  outline: 'none',
  userSelect: 'text',
  transition: 'border-color 0.1s, box-shadow 0.1s',
}
