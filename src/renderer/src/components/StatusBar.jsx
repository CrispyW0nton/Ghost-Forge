import React from 'react'
import { useSceneStore, useSettingsStore } from '../store'

export default function StatusBar() {
  const { objects, selectedIds, activeJob, viewportMode } = useSceneStore()
  const { aiApiKey, aiModel } = useSettingsStore()
  const selected = objects.find(o => selectedIds.includes(o.id))

  return (
    <div style={{
      height: 'var(--statusbar-h)',
      background: 'var(--gf-bg-1)',
      borderTop: '1px solid var(--gf-border)',
      display: 'flex', alignItems: 'center',
      padding: '0 12px', gap: 16,
      fontSize: 10, color: 'var(--gf-text-3)',
      flexShrink: 0, userSelect: 'none',
    }}>
      {/* Left: scene info */}
      <StatusItem>
        Objects: <b style={{ color: 'var(--gf-text-2)' }}>{objects.length}</b>
      </StatusItem>

      {selected && (
        <StatusItem>
          Selected: <b style={{ color: 'var(--gf-forge)' }}>{selected.name}</b>
        </StatusItem>
      )}

      {/* Active job */}
      {activeJob && (
        <StatusItem>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--gf-forge)',
            display: 'inline-block', marginRight: 4,
            animation: 'pulse 1s infinite',
          }}/>
          {activeJob.type}: {activeJob.stage} ({activeJob.progress}%)
        </StatusItem>
      )}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Right: view mode + AI status */}
      <StatusItem>
        View: <b style={{ color: 'var(--gf-text-2)', textTransform: 'capitalize' }}>{viewportMode}</b>
      </StatusItem>

      <StatusItem>
        AI: <b style={{ color: aiApiKey ? 'var(--gf-success)' : 'var(--gf-text-3)' }}>
          {aiApiKey ? aiModel : 'Offline'}
        </b>
      </StatusItem>

      {/* Credit */}
      <StatusItem>
        <span style={{ opacity: 0.4 }}>
          Based on <a href="https://github.com/lightningpixel/modly"
            target="_blank" style={{ color: 'var(--gf-ghost)', opacity: 0.6 }}>Modly</a> (MIT)
        </span>
      </StatusItem>
    </div>
  )
}

function StatusItem({ children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 3, whiteSpace: 'nowrap' }}>
      {children}
    </div>
  )
}
