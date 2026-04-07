import React, { useState, useEffect } from 'react'
import { useSceneStore, useSettingsStore } from '../store'

export default function StatusBar() {
  const { objects, selectedIds, activeJob, viewportMode } = useSceneStore()
  const { aiApiKey, aiModel } = useSettingsStore()
  const selected = objects.find(o => selectedIds.includes(o.id))
  const [time, setTime] = useState(() => new Date().toLocaleTimeString('en-US', { hour12: false }))

  // Live clock — matrix style
  useEffect(() => {
    const tick = setInterval(() => {
      setTime(new Date().toLocaleTimeString('en-US', { hour12: false }))
    }, 1000)
    return () => clearInterval(tick)
  }, [])

  return (
    <div style={{
      height: 'var(--statusbar-h)',
      background: 'var(--gf-bg-1)',
      borderTop: '1px solid var(--gf-border)',
      boxShadow: '0 -1px 0 #39FF1408',
      display: 'flex', alignItems: 'center',
      padding: '0 10px', gap: 14,
      fontSize: 9, color: 'var(--gf-text-3)',
      flexShrink: 0, userSelect: 'none',
      fontFamily: 'monospace', letterSpacing: '0.08em',
    }}>
      {/* Left: scene info */}
      <Stat
        label="OBJ"
        value={objects.length}
        valueColor="var(--gf-text-2)"
      />

      {selected && (
        <Stat
          label="SEL"
          value={selected.name.toUpperCase()}
          valueColor="var(--gf-neon)"
          glow
        />
      )}

      {/* Active job indicator */}
      {activeJob && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{
            width: 5, height: 5, borderRadius: '50%',
            background: 'var(--gf-neon)',
            boxShadow: '0 0 5px var(--gf-neon)',
            flexShrink: 0,
            animation: 'pulse 1s infinite',
          }}/>
          <span style={{ color: 'var(--gf-neon-dim)' }}>
            {activeJob.type}
          </span>
          <span style={{
            color: 'var(--gf-text-3)',
            fontSize: 8, background: 'var(--gf-bg-3)',
            border: '1px solid var(--gf-border)',
            padding: '0 4px', borderRadius: 1,
          }}>
            {activeJob.progress || 0}%
          </span>
        </div>
      )}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* View mode */}
      <Stat
        label="VIEW"
        value={viewportMode.toUpperCase()}
        valueColor="var(--gf-text-2)"
      />

      {/* AI status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{
          width: 4, height: 4, borderRadius: '50%',
          background: aiApiKey ? 'var(--gf-neon)' : 'var(--gf-text-4)',
          boxShadow: aiApiKey ? '0 0 4px var(--gf-neon)' : 'none',
          animation: aiApiKey ? 'pulse 3s ease infinite' : 'none',
        }}/>
        <span style={{ color: 'var(--gf-text-3)' }}>AI:</span>
        <span style={{
          color: aiApiKey ? 'var(--gf-neon)' : 'var(--gf-text-4)',
          textShadow: aiApiKey ? '0 0 4px var(--gf-neon)' : 'none',
        }}>
          {aiApiKey ? aiModel.split('-')[0].toUpperCase() : 'OFFLINE'}
        </span>
      </div>

      {/* Clock */}
      <span style={{
        color: 'var(--gf-text-4)',
        fontSize: 8,
        letterSpacing: '0.12em',
        fontFamily: 'monospace',
      }}>
        {time}
      </span>

      {/* Credit */}
      <span style={{ color: 'var(--gf-text-4)', fontSize: 8, opacity: 0.5 }}>
        //
        <a href="https://github.com/lightningpixel/modly"
           target="_blank"
           style={{ color: 'var(--gf-neon-dark)', textDecoration: 'none', marginLeft: 4 }}>
          MODLY
        </a>
      </span>
    </div>
  )
}

function Stat({ label, value, valueColor, glow }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap' }}>
      <span style={{ color: 'var(--gf-text-4)' }}>{label}:</span>
      <span style={{
        color: valueColor || 'var(--gf-text-2)',
        textShadow: glow ? '0 0 5px var(--gf-neon)' : 'none',
      }}>
        {value}
      </span>
    </div>
  )
}
