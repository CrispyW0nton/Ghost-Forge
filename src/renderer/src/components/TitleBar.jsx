import React, { useState, useEffect } from 'react'

// Ghost logo SVG
function GhostForgeLogo() {
  return (
    <svg width="20" height="20" viewBox="0 0 32 32" fill="none">
      {/* Forge flame */}
      <path d="M16 4 C16 4 22 10 22 17 C22 21 19 24 16 24 C13 24 10 21 10 17 C10 10 16 4 16 4Z"
            fill="url(#flame)" opacity="0.9"/>
      {/* Ghost body */}
      <path d="M10 14 C10 10 13 8 16 8 C19 8 22 10 22 14 L22 26 L19 24 L16 26 L13 24 L10 26 Z"
            fill="url(#ghost)" opacity="0.85"/>
      {/* Ghost eyes */}
      <circle cx="13.5" cy="17" r="1.5" fill="var(--gf-bg-base)"/>
      <circle cx="18.5" cy="17" r="1.5" fill="var(--gf-bg-base)"/>
      <defs>
        <linearGradient id="flame" x1="16" y1="4" x2="16" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ff9a5c"/>
          <stop offset="100%" stopColor="#ff6b2b"/>
        </linearGradient>
        <linearGradient id="ghost" x1="10" y1="8" x2="22" y2="26" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#a8a8ff"/>
          <stop offset="100%" stopColor="#6366f1"/>
        </linearGradient>
      </defs>
    </svg>
  )
}

export default function TitleBar() {
  const [maximized, setMaximized] = useState(false)
  const isElectron = !!window.ghostforge

  useEffect(() => {
    if (!isElectron) return
    window.ghostforge.window.isMaximized().then(setMaximized)
  }, [])

  return (
    <div
      className="drag-region flex items-center justify-between px-3 flex-shrink-0"
      style={{
        height: 'var(--titlebar-h)',
        background: 'var(--gf-bg-1)',
        borderBottom: '1px solid var(--gf-border)',
        zIndex: 100,
      }}
    >
      {/* Left: logo + name */}
      <div className="no-drag flex items-center gap-2">
        <GhostForgeLogo />
        <span style={{ fontWeight: 700, fontSize: 13, letterSpacing: '-0.3px' }}>
          <span style={{ color: 'var(--gf-ghost)' }}>Ghost</span>
          <span style={{ color: 'var(--gf-forge)' }}>Forge</span>
        </span>
        <span style={{
          fontSize: 10, color: 'var(--gf-text-3)',
          background: 'var(--gf-bg-3)', padding: '1px 6px',
          borderRadius: 4, marginLeft: 4
        }}>v0.1.0</span>
      </div>

      {/* Centre: file name (placeholder) */}
      <div style={{ fontSize: 12, color: 'var(--gf-text-3)' }}>
        Untitled Scene
      </div>

      {/* Right: window controls (electron only) */}
      <div className="no-drag flex items-center gap-1">
        {isElectron ? (
          <>
            <WinBtn onClick={() => window.ghostforge.window.minimize()} title="Minimise">
              <svg width="10" height="2" viewBox="0 0 10 2" fill="currentColor">
                <rect width="10" height="2" rx="1"/>
              </svg>
            </WinBtn>
            <WinBtn onClick={async () => {
              await window.ghostforge.window.maximize()
              setMaximized(await window.ghostforge.window.isMaximized())
            }} title={maximized ? 'Restore' : 'Maximise'}>
              {maximized
                ? <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="2" y="0" width="8" height="8" rx="1"/>
                    <rect x="0" y="2" width="8" height="8" rx="1" fill="var(--gf-bg-3)"/>
                  </svg>
                : <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="1" y="1" width="8" height="8" rx="1"/>
                  </svg>
              }
            </WinBtn>
            <WinBtn onClick={() => window.ghostforge.window.close()} title="Close" danger>
              <svg width="10" height="10" viewBox="0 0 10 10" stroke="currentColor" strokeWidth="1.5">
                <line x1="1" y1="1" x2="9" y2="9"/>
                <line x1="9" y1="1" x2="1" y2="9"/>
              </svg>
            </WinBtn>
          </>
        ) : (
          <span style={{ fontSize: 11, color: 'var(--gf-text-3)' }}>browser mode</span>
        )}
      </div>
    </div>
  )
}

function WinBtn({ children, onClick, title, danger }) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        width: 28, height: 22,
        background: 'transparent',
        border: 'none',
        borderRadius: 4,
        color: 'var(--gf-text-3)',
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.15s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = danger ? '#ef4444' : 'var(--gf-bg-3)'
        e.currentTarget.style.color = danger ? '#fff' : 'var(--gf-text)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = 'transparent'
        e.currentTarget.style.color = 'var(--gf-text-3)'
      }}
    >
      {children}
    </button>
  )
}
