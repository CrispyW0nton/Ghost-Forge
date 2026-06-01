import React, { useState, useEffect } from 'react'
import { useSceneStore, useSettingsStore } from '../store'
import { useRuntimeStore } from '../store/v2'

export default function StatusBar() {
  const { objects, selectedIds, activeJob, viewportMode } = useSceneStore()
  const { aiApiKey, aiModel } = useSettingsStore()
  const { gpus, scheduler, sessions, refresh } = useRuntimeStore()
  const selected = objects.find(o => selectedIds.includes(o.id))
  const [time, setTime] = useState(() => new Date().toLocaleTimeString('en-US', { hour12: false }))

  useEffect(() => {
    const tick = setInterval(() => {
      setTime(new Date().toLocaleTimeString('en-US', { hour12: false }))
    }, 1000)
    return () => clearInterval(tick)
  }, [])

  // Periodic runtime refresh — slow enough to feel passive but quick
  // enough that GPU/session state in the bar tracks reality. We avoid
  // forcing a torch re-detection (`refreshGpus: false`) so the cached
  // GPU listing is reused.
  useEffect(() => {
    refresh()
    const tick = setInterval(() => refresh(), 5000)
    return () => clearInterval(tick)
  }, [refresh])

  const cpuOnly = gpus?.cpu_only !== false
  const gpuCount = gpus?.gpus?.length || 0
  const sessionCount = Array.isArray(sessions) ? sessions.filter(s => s.loaded).length : 0
  const cpuInUse = scheduler?.cpu_in_use ?? 0
  const cpuTotal = scheduler?.cpu_concurrency ?? 0

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

      {/* Runtime indicators (P10) */}
      <Stat
        label="GPU"
        value={cpuOnly ? 'CPU' : `${gpuCount}×CUDA`}
        valueColor={cpuOnly ? 'var(--gf-text-3)' : 'var(--gf-cyan)'}
        glow={!cpuOnly}
        title={
          gpus && !cpuOnly
            ? gpus.gpus.map(g => `${g.name} (${(g.vram_mb/1024).toFixed(1)}GB)`).join('\n')
            : 'No CUDA GPU detected — workers fall back to CPU'
        }
      />

      {cpuTotal > 0 && (
        <Stat
          label="CPU"
          value={`${cpuInUse}/${cpuTotal}`}
          valueColor={cpuInUse > 0 ? 'var(--gf-neon)' : 'var(--gf-text-3)'}
          title="Scheduler CPU lane occupancy"
        />
      )}

      {sessionCount > 0 && (
        <Stat
          label="MEM"
          value={`${sessionCount} loaded`}
          valueColor="var(--gf-cyan)"
          glow
          title={
            sessions
              .filter(s => s.loaded)
              .map(s => `${s.name} (idle ${Math.round(s.idle_seconds || 0)}s)`)
              .join('\n')
          }
        />
      )}

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

function Stat({ label, value, valueColor, glow, title }) {
  return (
    <div
      title={title}
      style={{ display: 'flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap',
               cursor: title ? 'help' : 'default' }}
    >
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
