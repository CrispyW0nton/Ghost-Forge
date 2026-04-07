import React, { useState, useEffect } from 'react'

/* ── GhostForge Matrix Logo ─────────────────────────────────────────────────
   Ghost silhouette with glowing neon green eyes — based on Ghost's profile
*/
function GhostForgeLogo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      {/* Hood / cloak shape */}
      <path
        d="M4 30 L4 16 C4 8 9 3 16 3 C23 3 28 8 28 16 L28 30 L24 27 L20 30 L16 27 L12 30 L8 27 Z"
        fill="#050D05"
        stroke="#39FF14"
        strokeWidth="0.8"
        opacity="0.9"
      />
      {/* Hood inner shadow */}
      <path
        d="M7 28 L7 17 C7 11 11 6 16 6 C21 6 25 11 25 17 L25 28 L22 26 L16 28 L10 26 Z"
        fill="#020402"
        opacity="0.95"
      />
      {/* Left eye — glowing */}
      <ellipse cx="12.5" cy="17" rx="2.2" ry="1.6" fill="#39FF14"
        style={{ filter: 'drop-shadow(0 0 4px #39FF14) drop-shadow(0 0 8px #2CFF2C)' }}
      />
      {/* Right eye — glowing */}
      <ellipse cx="19.5" cy="17" rx="2.2" ry="1.6" fill="#39FF14"
        style={{ filter: 'drop-shadow(0 0 4px #39FF14) drop-shadow(0 0 8px #2CFF2C)' }}
      />
      {/* Eye inner glow cores */}
      <ellipse cx="12.5" cy="17" rx="1" ry="0.8" fill="#B8FFB8" opacity="0.8"/>
      <ellipse cx="19.5" cy="17" rx="1" ry="0.8" fill="#B8FFB8" opacity="0.8"/>
      {/* Neon edge outline on hood */}
      <path
        d="M4 30 L4 16 C4 8 9 3 16 3 C23 3 28 8 28 16 L28 30"
        fill="none"
        stroke="#39FF14"
        strokeWidth="0.5"
        opacity="0.4"
        strokeDasharray="2 3"
      />
    </svg>
  )
}

export default function TitleBar() {
  const [maximized, setMaximized] = useState(false)
  const [glitch, setGlitch]       = useState(false)
  const isElectron = !!window.ghostforge

  useEffect(() => {
    if (!isElectron) return
    window.ghostforge.window.isMaximized().then(setMaximized)
  }, [])

  // Occasional glitch effect on the title
  useEffect(() => {
    const interval = setInterval(() => {
      setGlitch(true)
      setTimeout(() => setGlitch(false), 200)
    }, 8000 + Math.random() * 4000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div
      className="drag-region flex items-center justify-between flex-shrink-0"
      style={{
        height: 'var(--titlebar-h)',
        background: 'var(--gf-bg-1)',
        borderBottom: '1px solid var(--gf-border)',
        boxShadow: '0 1px 0 #39FF1415',
        zIndex: 100,
        padding: '0 10px',
      }}
    >
      {/* ── Left: Logo + Name ── */}
      <div className="no-drag flex items-center gap-2">
        <div className="animate-eye-glow">
          <GhostForgeLogo size={26} />
        </div>

        <div style={{ position: 'relative' }}>
          {/* Main title */}
          <span style={{
            fontWeight: 700,
            fontSize: 14,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--gf-neon)',
            textShadow: '0 0 8px var(--gf-neon), 0 0 20px var(--gf-neon-glow)',
            fontFamily: "'Courier New', monospace",
          }}>
            Ghost<span style={{ color: 'var(--gf-neon-bright)' }}>Forge</span>
          </span>

          {/* Glitch overlay */}
          {glitch && (
            <span aria-hidden style={{
              position: 'absolute', top: 0, left: 0,
              color: '#FF2D55',
              fontWeight: 700, fontSize: 14,
              letterSpacing: '0.08em', textTransform: 'uppercase',
              fontFamily: "'Courier New', monospace",
              animation: 'glitch 0.2s steps(1) forwards',
              opacity: 0.7,
              mixBlendMode: 'screen',
            }}>
              GhostForge
            </span>
          )}
        </div>

        <span style={{
          fontSize: 9,
          color: 'var(--gf-text-3)',
          background: 'var(--gf-bg-3)',
          border: '1px solid var(--gf-border)',
          padding: '1px 5px',
          borderRadius: 2,
          letterSpacing: '0.1em',
          fontFamily: 'monospace',
        }}>
          v0.1.0
        </span>
      </div>

      {/* ── Centre: status ── */}
      <div style={{
        fontSize: 10,
        color: 'var(--gf-text-3)',
        letterSpacing: '0.15em',
        textTransform: 'uppercase',
        fontFamily: 'monospace',
      }}>
        <span style={{ color: 'var(--gf-text-4)' }}>// </span>
        UNTITLED_SCENE
        <span style={{ color: 'var(--gf-text-4)' }}> //</span>
      </div>

      {/* ── Right: window controls ── */}
      <div className="no-drag flex items-center gap-1">
        {isElectron ? (
          <>
            <WinBtn onClick={() => window.ghostforge.window.minimize()} title="Minimise">
              <svg width="8" height="1.5" viewBox="0 0 8 1.5" fill="currentColor">
                <rect width="8" height="1.5" rx="0.75"/>
              </svg>
            </WinBtn>
            <WinBtn onClick={async () => {
              await window.ghostforge.window.maximize()
              setMaximized(await window.ghostforge.window.isMaximized())
            }} title={maximized ? 'Restore' : 'Maximise'}>
              <svg width="9" height="9" viewBox="0 0 9 9" fill="none"
                   stroke="currentColor" strokeWidth="1.2">
                <rect x="0.6" y="0.6" width="7.8" height="7.8" rx="0.8"/>
              </svg>
            </WinBtn>
            <WinBtn onClick={() => window.ghostforge.window.close()} title="Close" danger>
              <svg width="9" height="9" viewBox="0 0 9 9" stroke="currentColor" strokeWidth="1.5">
                <line x1="1" y1="1" x2="8" y2="8"/>
                <line x1="8" y1="1" x2="1" y2="8"/>
              </svg>
            </WinBtn>
          </>
        ) : (
          <span style={{ fontSize: 9, color: 'var(--gf-text-4)', letterSpacing: '0.1em' }}>
            [BROWSER_MODE]
          </span>
        )}
      </div>
    </div>
  )
}

function WinBtn({ children, onClick, title, danger }) {
  const [hover, setHover] = useState(false)
  return (
    <button
      onClick={onClick}
      title={title}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: 26, height: 20,
        background: hover
          ? danger ? 'rgba(255,45,85,0.2)' : 'var(--gf-bg-4)'
          : 'transparent',
        border: `1px solid ${hover ? (danger ? 'var(--gf-danger)' : 'var(--gf-border-h)') : 'transparent'}`,
        borderRadius: 3,
        color: hover
          ? danger ? 'var(--gf-danger)' : 'var(--gf-neon)'
          : 'var(--gf-text-3)',
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.12s',
        boxShadow: hover && !danger ? '0 0 6px #39FF1433' : 'none',
      }}
    >
      {children}
    </button>
  )
}
