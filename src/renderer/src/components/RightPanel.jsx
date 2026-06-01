import React, { useState, useEffect } from 'react'
import { useUIStore, useSceneStore, useSettingsStore } from '../store'
import {
  useAuditStore, useEnginesStore, useAuthoringStore, useRetargetStore,
} from '../store/v2'
import {
  createUVTextureJob, pollJob,
  getPreviewUrl, getDownloadUrl, getGlbPreviewUrl,
} from '../modules/api'

// ─── Shared sub-components ────────────────────────────────────────────────────

function Section({ label, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{
        fontSize: 9, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.14em', color: 'var(--gf-text-3)',
        fontFamily: 'monospace',
        padding: '3px 0 5px',
        borderBottom: '1px solid var(--gf-border)',
        marginBottom: 8,
        display: 'flex', alignItems: 'center', gap: 5,
      }}>
        <span style={{ color: 'var(--gf-neon-dim)' }}>//</span>
        {label}
      </div>
      {children}
    </div>
  )
}

function PropRow({ label, value, valueColor }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between',
      padding: '4px 0', fontSize: 11,
      borderBottom: '1px solid rgba(57,255,20,0.04)',
    }}>
      <span style={{ color: 'var(--gf-text-3)', fontFamily: 'monospace', letterSpacing: '0.05em' }}>{label}</span>
      <span style={{ color: valueColor || 'var(--gf-text-2)', fontFamily: 'monospace' }}>{value}</span>
    </div>
  )
}

function Vec3Row({ label, values }) {
  const axisColors = ['#FF2D55', '#39FF14', '#00E5FF']
  return (
    <div style={{ marginBottom: 8 }}>
      <span style={{
        fontSize: 9, color: 'var(--gf-text-3)', display: 'block',
        marginBottom: 4, fontFamily: 'monospace', letterSpacing: '0.1em',
        textTransform: 'uppercase',
      }}>{label}</span>
      <div style={{ display: 'flex', gap: 4 }}>
        {['X','Y','Z'].map((axis, i) => (
          <div key={axis} style={{
            flex: 1, display: 'flex', alignItems: 'center',
            background: 'var(--gf-bg-3)',
            border: '1px solid var(--gf-border)',
            borderRadius: 'var(--gf-radius-sm)',
            overflow: 'hidden',
          }}>
            <span style={{
              padding: '0 5px', fontSize: 9, color: axisColors[i],
              fontWeight: 700, borderRight: '1px solid var(--gf-border)',
              fontFamily: 'monospace', lineHeight: '26px',
              textShadow: `0 0 5px ${axisColors[i]}88`,
            }}>{axis}</span>
            <input type="number" defaultValue={values[i]} style={{
              width: '100%', background: 'transparent', border: 'none',
              color: 'var(--gf-text-2)', fontSize: 10,
              padding: '3px 4px', textAlign: 'right',
              fontFamily: 'monospace',
            }}/>
          </div>
        ))}
      </div>
    </div>
  )
}

function FieldRow({ label, children }) {
  return (
    <div style={{ marginBottom: 9 }}>
      <span style={{
        fontSize: 9, color: 'var(--gf-text-3)', display: 'block',
        marginBottom: 4, fontFamily: 'monospace', letterSpacing: '0.1em',
        textTransform: 'uppercase',
      }}>{label}</span>
      {children}
    </div>
  )
}

function MatrixActionBtn({ onClick, disabled, loading, label, color }) {
  const [hover, setHover] = useState(false)
  const c = color || 'var(--gf-neon)'
  const cd = color || '#39FF14'
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: '100%', height: 32,
        background: disabled ? 'transparent'
          : hover ? `rgba(57,255,20,0.18)` : `rgba(57,255,20,0.09)`,
        border: `1px solid ${disabled ? 'var(--gf-border)' : hover ? cd : 'var(--gf-neon-dim)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        color: disabled ? 'var(--gf-text-4)' : c,
        fontSize: 9, fontWeight: 700, fontFamily: 'monospace',
        letterSpacing: '0.15em', textTransform: 'uppercase',
        cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        transition: 'all 0.1s',
        boxShadow: disabled ? 'none' : hover
          ? `0 0 14px ${cd}40, inset 0 0 8px ${cd}08`
          : `0 0 6px ${cd}20`,
        textShadow: disabled ? 'none' : `0 0 6px ${c}`,
      }}
    >
      {loading && (
        <div className="animate-spin" style={{
          width: 10, height: 10, flexShrink: 0,
          border: '1.5px solid rgba(57,255,20,0.25)',
          borderTopColor: 'var(--gf-neon)',
          borderRadius: '50%',
          boxShadow: '0 0 4px var(--gf-neon)',
        }}/>
      )}
      <span>&gt; {label}</span>
    </button>
  )
}

function ProgressBar({ stage, pct }) {
  return (
    <div style={{
      background: 'var(--gf-bg-2)',
      border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius-sm)',
      padding: '8px 10px',
      boxShadow: 'inset 0 0 10px rgba(57,255,20,0.03)',
    }}>
      <div style={{
        fontSize: 9, color: 'var(--gf-text-2)',
        marginBottom: 6, fontFamily: 'monospace',
        letterSpacing: '0.08em', textTransform: 'uppercase',
      }}>
        <span style={{ color: 'var(--gf-neon-dim)' }}>&gt;&gt; </span>
        {stage}
      </div>
      <div style={{ height: 3, background: 'var(--gf-bg-3)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${pct || 0}%`,
          background: 'linear-gradient(90deg, var(--gf-neon-dim), var(--gf-neon), var(--gf-neon-bright))',
          boxShadow: '0 0 6px var(--gf-neon), 0 0 12px #39FF1444',
          borderRadius: 2,
          transition: 'width 0.35s ease',
        }}/>
      </div>
      <div style={{
        textAlign: 'right', marginTop: 4,
        fontSize: 9, color: 'var(--gf-neon)',
        fontFamily: 'monospace', fontWeight: 700,
        textShadow: '0 0 5px var(--gf-neon)',
      }}>{pct || 0}%</div>
    </div>
  )
}

function MatrixToggle({ checked, onChange }) {
  return (
    <div
      onClick={() => onChange(!checked)}
      style={{
        width: 36, height: 20, borderRadius: 10,
        background: checked ? 'rgba(57,255,20,0.15)' : 'var(--gf-bg-3)',
        border: `1px solid ${checked ? 'var(--gf-neon-dim)' : 'var(--gf-border-h)'}`,
        boxShadow: checked ? '0 0 8px #39FF1430' : 'none',
        cursor: 'pointer', position: 'relative',
        transition: 'all 0.2s', flexShrink: 0,
      }}
    >
      <div style={{
        position: 'absolute', top: 2,
        left: checked ? 17 : 2,
        width: 14, height: 14, borderRadius: '50%',
        background: checked ? 'var(--gf-neon)' : 'var(--gf-text-3)',
        boxShadow: checked ? '0 0 6px var(--gf-neon)' : 'none',
        transition: 'left 0.2s, background 0.2s',
      }}/>
    </div>
  )
}

const matrixSelect = {
  width: '100%',
  background: 'var(--gf-bg-3)',
  border: '1px solid var(--gf-border-h)',
  borderRadius: 'var(--gf-radius-sm)',
  color: 'var(--gf-text)',
  fontSize: 11,
  padding: '5px 7px',
  fontFamily: 'monospace',
  cursor: 'pointer',
}

function Empty({ msg }) {
  return (
    <div style={{
      padding: '30px 16px', textAlign: 'center',
      color: 'var(--gf-text-4)', fontSize: 9,
      fontFamily: 'monospace', letterSpacing: '0.1em',
      lineHeight: 2,
    }}>
      <div style={{ color: 'var(--gf-neon-dim)', marginBottom: 6, fontSize: 16 }}>⊙</div>
      <div style={{ textTransform: 'uppercase' }}>{msg}</div>
    </div>
  )
}

// ─── Download button row ──────────────────────────────────────────────────────
function DownloadBtn({ label, onClick, colorKey }) {
  const [hover, setHover] = useState(false)
  const colors = {
    neon:  { base: '#39FF14', dim: 'rgba(57,255,20,0.12)' },
    cyan:  { base: '#00E5FF', dim: 'rgba(0,229,255,0.12)' },
    pink:  { base: '#FF2D55', dim: 'rgba(255,45,85,0.12)' },
  }
  const c = colors[colorKey] || colors.neon
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        flex: 1, height: 28,
        background: hover ? c.dim : 'rgba(57,255,20,0.04)',
        border: `1px solid ${hover ? c.base : 'var(--gf-border-h)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        color: hover ? c.base : 'var(--gf-text-2)',
        fontSize: 8, fontFamily: 'monospace',
        letterSpacing: '0.1em', textTransform: 'uppercase',
        cursor: 'pointer',
        transition: 'all 0.12s',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
        textShadow: hover ? `0 0 5px ${c.base}` : 'none',
        boxShadow: hover ? `0 0 8px ${c.base}40` : 'none',
      }}
    >
      <span style={{ fontSize: 10 }}>↓</span>
      {label}
    </button>
  )
}

// ─── Job complete — outputs panel ─────────────────────────────────────────────
function JobOutputPanel({ jobId, hasTexture }) {
  const triggerDownload = (url, filename) => {
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  return (
    <div style={{
      marginTop: 10,
      background: 'rgba(57,255,20,0.03)',
      border: '1px solid rgba(57,255,20,0.2)',
      borderRadius: 'var(--gf-radius-sm)',
      padding: '8px 9px',
      boxShadow: '0 0 12px rgba(57,255,20,0.08)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        marginBottom: 7, fontSize: 9,
        fontFamily: 'monospace', letterSpacing: '0.1em',
      }}>
        <span style={{
          display: 'inline-block', width: 6, height: 6,
          borderRadius: '50%', background: '#39FF14',
          boxShadow: '0 0 6px #39FF14', flexShrink: 0,
        }}/>
        <span style={{ color: 'var(--gf-neon)', textTransform: 'uppercase' }}>JOB_COMPLETE</span>
        <span style={{ color: 'var(--gf-text-4)', marginLeft: 'auto' }}>{jobId?.slice(0, 8)}…</span>
      </div>

      {/* Download buttons */}
      <div style={{ display: 'flex', gap: 4 }}>
        <DownloadBtn
          label="MESH.GLB"
          colorKey="neon"
          onClick={() => triggerDownload(getDownloadUrl(jobId, 'mesh'), 'ghostforge_mesh.glb')}
        />
        {hasTexture && (
          <DownloadBtn
            label="TEX.PNG"
            colorKey="cyan"
            onClick={() => triggerDownload(getDownloadUrl(jobId, 'texture'), 'ghostforge_texture.png')}
          />
        )}
        <DownloadBtn
          label="UV.PNG"
          colorKey="pink"
          onClick={() => triggerDownload(getDownloadUrl(jobId, 'uv_layout'), 'ghostforge_uv_layout.png')}
        />
      </div>
    </div>
  )
}

// ─── Tab button ───────────────────────────────────────────────────────────────
function TabBtn({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      flex: 1, height: 34,
      background: active ? 'var(--gf-bg-3)' : 'transparent',
      border: 'none',
      borderBottom: active
        ? '2px solid var(--gf-neon)'
        : '2px solid transparent',
      color: active ? 'var(--gf-neon)' : 'var(--gf-text-3)',
      fontSize: 9, fontWeight: 700,
      textTransform: 'uppercase', letterSpacing: '0.12em',
      cursor: 'pointer', transition: 'all 0.1s',
      fontFamily: 'monospace',
      textShadow: active ? '0 0 6px var(--gf-neon)' : 'none',
      boxShadow: active ? 'inset 0 -1px 0 #39FF1430' : 'none',
    }}>
      {label}
    </button>
  )
}

// ─── Main RightPanel ─────────────────────────────────────────────────────────
export default function RightPanel() {
  const { activeRightTab, setRightTab } = useUIStore()
  const { selectedIds, objects } = useSceneStore()
  const selected = objects.find(o => selectedIds.includes(o.id)) || null

  return (
    <div style={{
      width: 'var(--right-panel-w)',
      background: 'var(--gf-bg-1)',
      borderLeft: '1px solid var(--gf-border)',
      boxShadow: '-1px 0 0 #39FF1408',
      display: 'flex', flexDirection: 'column',
      flexShrink: 0, overflow: 'hidden',
    }}>
      {/* Tab bar */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid var(--gf-border)',
        flexShrink: 0,
        background: 'var(--gf-bg-1)',
      }}>
        <TabBtn label="PROPS"   active={activeRightTab === 'properties'} onClick={() => setRightTab('properties')} />
        <TabBtn label="UV"      active={activeRightTab === 'uv'}         onClick={() => setRightTab('uv')} />
        <TabBtn label="TEX"     active={activeRightTab === 'texture'}    onClick={() => setRightTab('texture')} />
        <TabBtn label="MODS"    active={activeRightTab === 'modifiers'}  onClick={() => setRightTab('modifiers')} />
        <TabBtn label="AUDIT"   active={activeRightTab === 'audit'}      onClick={() => setRightTab('audit')} />
        <TabBtn label="ENGINE"  active={activeRightTab === 'engine'}     onClick={() => setRightTab('engine')} />
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {activeRightTab === 'properties' && <PropertiesTab selected={selected} />}
        {activeRightTab === 'uv'         && <UVTab         selected={selected} />}
        {activeRightTab === 'texture'    && <TextureTab    selected={selected} />}
        {activeRightTab === 'modifiers'  && <ModifiersTab  selected={selected} />}
        {activeRightTab === 'audit'      && <AuditTab      selected={selected} />}
        {activeRightTab === 'engine'     && <EngineTab     selected={selected} />}
      </div>
    </div>
  )
}

// ─── Properties Tab ───────────────────────────────────────────────────────────
function PropertiesTab({ selected }) {
  if (!selected) return <Empty msg="Select an object to view properties" />

  const stats = selected.meshStats || {}

  return (
    <div style={{ padding: 10 }}>
      <Section label="OBJECT_INFO">
        <PropRow label="NAME"    value={selected.name} />
        <PropRow label="TYPE"    value={selected.type || 'MESH'} />
        <PropRow
          label="UV_STATE"
          value={selected.uvDone ? '✓ UNWRAPPED' : '✗ NONE'}
          valueColor={selected.uvDone ? 'var(--gf-neon)' : 'var(--gf-text-3)'}
        />
        <PropRow
          label="TEX_STATE"
          value={selected.textureDone ? '✓ APPLIED' : '✗ NONE'}
          valueColor={selected.textureDone ? 'var(--gf-cyan)' : 'var(--gf-text-3)'}
        />
      </Section>

      {/* Mesh Stats — shown once available from backend /api/mesh-info */}
      {(stats.vertices != null || stats.loading) && (
        <Section label="MESH_STATS">
          {stats.loading ? (
            <div style={{
              fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
              letterSpacing: '0.08em', padding: '4px 0',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <div className="animate-spin" style={{
                width: 8, height: 8, border: '1.5px solid rgba(57,255,20,0.2)',
                borderTopColor: 'var(--gf-neon)', borderRadius: '50%',
              }}/>
              PARSING MESH…
            </div>
          ) : (
            <>
              <PropRow
                label="VERTICES"
                value={stats.vertices?.toLocaleString() ?? '—'}
                valueColor="var(--gf-neon)"
              />
              <PropRow
                label="FACES"
                value={stats.faces?.toLocaleString() ?? '—'}
                valueColor="var(--gf-text-2)"
              />
              {stats.edges != null && (
                <PropRow label="EDGES" value={stats.edges?.toLocaleString() ?? '—'} />
              )}
              <PropRow
                label="WATERTIGHT"
                value={stats.watertight ? '✓ YES' : '✗ NO'}
                valueColor={stats.watertight ? 'var(--gf-neon)' : 'var(--gf-text-3)'}
              />
              {stats.size && (
                <PropRow
                  label="DIMENSIONS"
                  value={stats.size.map(v => v.toFixed(2)).join(' × ')}
                  valueColor="var(--gf-text-2)"
                />
              )}
              {stats.format && (
                <PropRow label="FORMAT" value={stats.format.toUpperCase()} />
              )}
            </>
          )}
        </Section>
      )}

      <Section label="TRANSFORM">
        <Vec3Row label="POSITION" values={[0, 0, 0]} />
        <Vec3Row label="ROTATION" values={[0, 0, 0]} />
        <Vec3Row label="SCALE"    values={[1, 1, 1]} />
      </Section>

      {selected.uvDone && (
        <div style={{
          padding: '6px 8px', marginTop: 4,
          background: 'rgba(57,255,20,0.04)',
          border: '1px solid rgba(57,255,20,0.15)',
          borderRadius: 'var(--gf-radius-sm)',
          fontSize: 9, color: 'var(--gf-neon-dim)',
          fontFamily: 'monospace', letterSpacing: '0.08em',
        }}>
          &gt; UV_ATLAS: READY — switch to UV tab
        </div>
      )}

      {/* Download outputs when job is done */}
      {selected.jobId && selected.uvDone && (
        <div style={{ marginTop: 10 }}>
          <JobOutputPanel jobId={selected.jobId} hasTexture={selected.textureDone} />
        </div>
      )}
    </div>
  )
}

// ─── UV Tab ──────────────────────────────────────────────────────────────────
function UVTab({ selected }) {
  const [atlasSize, setAtlasSize]   = useState(1024)
  const [padding, setPadding]       = useState(2)
  const [forceUnwrap, setForce]     = useState(false)
  const [running, setRunning]       = useState(false)
  const [progress, setProgress]     = useState(null)
  const [uvPreview, setUvPreview]   = useState(null)
  const [doneJobId, setDoneJobId]   = useState(null)
  const [lastResult, setLastResult] = useState(null)
  const { updateObject, setActiveJob, clearActiveJob } = useSceneStore()

  if (!selected) return <Empty msg="Select an object to unwrap UVs" />

  const handleUnwrap = async () => {
    if (!selected.file) return
    setRunning(true)
    setDoneJobId(null)
    setUvPreview(null)
    setLastResult(null)
    setProgress({ stage: 'INITIALISING', progress: 0 })

    try {
      const job = await createUVTextureJob({
        meshFile:    selected.file,
        prompt:      'uv unwrap only',
        textureSize: atlasSize,
        outputFormat:'glb',
        uvOnly:      true,
        forceUnwrap,
      })
      setActiveJob({ id: job.job_id, type: 'UV_UNWRAP', status: 'running', progress: 0, stage: 'STARTING' })

      pollJob(
        job.job_id,
        (j) => { setProgress(j); setActiveJob({ id: j.id, type: 'UV_UNWRAP', ...j }) },
        (j) => {
          setRunning(false)
          setProgress(j)
          clearActiveJob()
          setDoneJobId(j.id)
          setUvPreview(getPreviewUrl(j.id, 'uv_layout'))
          setLastResult(j.result)
          updateObject(selected.id, {
            uvDone: true,
            jobId:  j.id,
            previewUrl: getGlbPreviewUrl(j.id),
          })
        },
        (err) => {
          setRunning(false)
          setProgress({ stage: `ERR: ${err.message}`, progress: 0 })
          clearActiveJob()
        }
      )
    } catch (e) {
      setRunning(false)
      setProgress({ stage: `ERR: ${e.message}`, progress: 0 })
    }
  }

  const wasDecimated  = lastResult?.uv_stats?.decimated
  const skippedUnwrap = lastResult?.uv_stats?.skipped_unwrap
  const origFaces     = lastResult?.original_stats?.faces
  const uvVerts       = lastResult?.uv_stats?.unwrapped_vertices

  return (
    <div style={{ padding: 10 }}>
      <Section label="UV_UNWRAP_SETTINGS">
        <FieldRow label="ATLAS_SIZE">
          <select value={atlasSize} onChange={e => setAtlasSize(+e.target.value)} style={matrixSelect}>
            <option value={512}>512 × 512</option>
            <option value={1024}>1024 × 1024</option>
            <option value={2048}>2048 × 2048</option>
          </select>
        </FieldRow>

        <FieldRow label={`ISLAND_PADDING: ${padding}px`}>
          <input
            type="range" min={1} max={8} value={padding}
            onChange={e => setPadding(+e.target.value)}
            style={{ width: '100%' }}
          />
        </FieldRow>

        <FieldRow label="FORCE_RE-UNWRAP">
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <MatrixToggle checked={forceUnwrap} onChange={setForce} />
            <span style={{
              fontSize: 9, fontFamily: 'monospace', letterSpacing: '0.07em',
              color: forceUnwrap ? 'var(--gf-neon)' : 'var(--gf-text-3)',
              textShadow: forceUnwrap ? '0 0 5px var(--gf-neon)' : 'none',
            }}>
              {forceUnwrap ? 'ALWAYS_REGENERATE_UVs' : 'REUSE_IF_PRESENT'}
            </span>
          </div>
        </FieldRow>
      </Section>

      {/* Algorithm info */}
      <div style={{
        padding: '6px 8px', marginBottom: 10,
        background: 'rgba(0,229,255,0.04)',
        border: '1px solid rgba(0,229,255,0.15)',
        borderRadius: 'var(--gf-radius-sm)',
        fontSize: 9, color: 'var(--gf-cyan-dim)',
        fontFamily: 'monospace', letterSpacing: '0.06em',
        lineHeight: 1.7,
      }}>
        // Algorithm: xatlas ABF++ (subprocess-isolated)<br/>
        // Safe limit: &lt;100k faces — auto-decimates above
      </div>

      <MatrixActionBtn
        onClick={handleUnwrap}
        disabled={running || !selected.file}
        loading={running}
        label="AUTO_UNWRAP_UVs"
      />

      {progress && (
        <div style={{ marginTop: 10 }}>
          <ProgressBar stage={progress.stage} pct={progress.progress} />
        </div>
      )}

      {/* Post-job status pills */}
      {lastResult && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
          {wasDecimated && (
            <div style={{
              padding: '3px 8px', fontSize: 8, fontFamily: 'monospace',
              background: 'rgba(255,165,0,0.12)',
              border: '1px solid rgba(255,165,0,0.4)',
              borderRadius: 2, color: '#FFA500',
              letterSpacing: '0.07em',
            }}>
              ⚠ DECIMATED: {origFaces?.toLocaleString()} → ~18k faces
            </div>
          )}
          {skippedUnwrap && (
            <div style={{
              padding: '3px 8px', fontSize: 8, fontFamily: 'monospace',
              background: 'rgba(0,229,255,0.08)',
              border: '1px solid rgba(0,229,255,0.3)',
              borderRadius: 2, color: 'var(--gf-cyan)',
              letterSpacing: '0.07em',
            }}>
              ✓ REUSED_EXISTING_UVs
            </div>
          )}
          {uvVerts && (
            <div style={{
              padding: '3px 8px', fontSize: 8, fontFamily: 'monospace',
              background: 'rgba(57,255,20,0.06)',
              border: '1px solid var(--gf-border)',
              borderRadius: 2, color: 'var(--gf-text-3)',
              letterSpacing: '0.07em',
            }}>
              {uvVerts?.toLocaleString()} UV verts
            </div>
          )}
        </div>
      )}

      {uvPreview && (
        <div style={{ marginTop: 14 }}>
          <Section label="UV_LAYOUT_PREVIEW">
            <div style={{
              border: '1px solid var(--gf-neon-dim)',
              borderRadius: 'var(--gf-radius-sm)',
              overflow: 'hidden',
              boxShadow: '0 0 10px #39FF1420',
            }}>
              <img src={uvPreview} style={{ width: '100%', display: 'block' }} alt="UV Layout" />
            </div>
          </Section>

          {doneJobId && (
            <JobOutputPanel jobId={doneJobId} hasTexture={false} />
          )}
        </div>
      )}
    </div>
  )
}

// ─── Texture Tab ──────────────────────────────────────────────────────────────
function TextureTab({ selected }) {
  const [prompt, setPrompt]         = useState('worn surface, detailed PBR material')
  const [texSize, setTexSize]       = useState(1024)
  const [useAI, setUseAI]           = useState(false)
  const [aiSteps, setAiSteps]       = useState(20)
  const [running, setRunning]       = useState(false)
  const [progress, setProgress]     = useState(null)
  const [texPreview, setTexPreview] = useState(null)
  const [refFile, setRefFile]       = useState(null)
  const [doneJobId, setDoneJobId]   = useState(null)
  const refInput = React.useRef()
  const { updateObject, setActiveJob, clearActiveJob } = useSceneStore()

  if (!selected) return <Empty msg="Select an object to generate textures" />

  const handleGenerate = async () => {
    if (!selected.file) return
    setRunning(true)
    setDoneJobId(null)
    setTexPreview(null)
    setProgress({ stage: 'INITIALISING', progress: 0 })

    try {
      const job = await createUVTextureJob({
        meshFile: selected.file,
        prompt,
        referenceFile: refFile,
        textureSize: texSize,
        useAI,
        aiSteps,
        outputFormat: 'glb',
      })
      setActiveJob({ id: job.job_id, type: 'TEX_GEN', status: 'running', progress: 0, stage: 'STARTING' })

      pollJob(
        job.job_id,
        (j) => { setProgress(j); setActiveJob({ id: j.id, type: 'TEX_GEN', ...j }) },
        (j) => {
          setRunning(false)
          setProgress(j)
          clearActiveJob()
          setDoneJobId(j.id)
          setTexPreview(getPreviewUrl(j.id, 'texture'))
          // Auto-load textured GLB in viewport
          updateObject(selected.id, {
            uvDone: true,
            textureDone: true,
            texturePrompt: prompt,
            jobId: j.id,
            previewUrl: getGlbPreviewUrl(j.id),
          })
        },
        (err) => {
          setRunning(false)
          setProgress({ stage: `ERR: ${err.message}`, progress: 0 })
          clearActiveJob()
        }
      )
    } catch (e) {
      setRunning(false)
      setProgress({ stage: `ERR: ${e.message}`, progress: 0 })
    }
  }

  // Grouped material quick-prompts (v1.4 — 40+ presets across 8 categories)
  const quickPromptGroups = [
    {
      label: 'METALS',
      color: '#B0C4DE',
      prompts: [
        ['STEEL',     'brushed steel, industrial metal, fine scratches'],
        ['RUST',      'rusted iron, oxidised, heavy corrosion, surface decay'],
        ['CHROME',    'mirror chrome, polished reflective metal'],
        ['GOLD',      'polished gold, metallic sheen, luxury finish'],
        ['COPPER',    'aged copper, patina, green oxidation'],
        ['BRONZE',    'cast bronze, antique finish, dark patina'],
        ['SILVER',    'polished silver, clean reflective surface'],
        ['TITANIUM',  'dark titanium, gunmetal, aerospace alloy'],
        ['ROSE GOLD', 'rose gold, pink gold, warm metallic'],
      ],
    },
    {
      label: 'WOOD',
      color: '#C8A96E',
      prompts: [
        ['OAK',       'aged oak wood grain, natural knots, warm tones'],
        ['WALNUT',    'dark walnut wood, fine grain, rich brown'],
        ['PINE',      'light pine wood, pale grain, knots'],
        ['MAHOGANY',  'mahogany wood, reddish-brown, polished'],
        ['EBONY',     'ebony wood, dark exotic grain, near-black'],
        ['BAMBOO',    'bamboo stalk, pale green-yellow, segmented'],
        ['DRIFTWOOD', 'driftwood, bleached wood, weathered, cracked pale'],
        ['BARK',      'rough tree bark, ridged, dark brown, mossy bark'],
      ],
    },
    {
      label: 'STONE',
      color: '#A0A0A8',
      prompts: [
        ['MARBLE',    'polished marble, white veins, luxury stone surface'],
        ['GRANITE',   'grey granite, speckled, granite vein pattern'],
        ['SANDSTONE', 'sandstone, warm layered sedimentary rock, ochre'],
        ['OBSIDIAN',  'obsidian, volcanic glass, dark glossy black'],
        ['COBBLE',    'cobblestone, irregular paving stones, mortar'],
        ['SLATE',     'dark slate, layered metamorphic rock, flat'],
        ['CONCRETE',  'raw concrete, grey, brutalist, rough texture'],
        ['COAL',      'coal, charcoal, dark glossy mineral'],
        ['GRAVEL',    'gravel, crushed stone aggregate, rough ground'],
      ],
    },
    {
      label: 'ORGANIC',
      color: '#7DBF7D',
      prompts: [
        ['LEATHER',   'dark leather, stitched seams, worn tactile surface'],
        ['VELVET',    'red velvet, deep plush fabric, luxury'],
        ['DENIM',     'blue denim fabric, woven cloth, textile'],
        ['SCALES',    'dragon scales, iridescent reptile armour'],
        ['FUR',       'grey wolf fur, short dense animal pelt'],
        ['TIGER FUR', 'tiger fur, orange and black stripes'],
        ['MOSS',      'green moss, soft organic growth, damp surface'],
        ['BARK MOSS', 'mossy bark, lichen covered tree bark'],
      ],
    },
    {
      label: 'GROUND',
      color: '#A0784A',
      prompts: [
        ['SAND',      'desert sand, fine grain, warm ochre dunes'],
        ['MUD',       'wet mud, clay, dark moist earth'],
        ['SOIL',      'dark soil, earth, rich dirt ground'],
        ['GRUNGE',    'grunge, dirty stained surface, grime layers'],
      ],
    },
    {
      label: 'SCI-FI',
      color: '#39FF14',
      prompts: [
        ['MATRIX',    'dark circuit board, green neon traces, cyberpunk tech'],
        ['CARBON',    'carbon fiber weave, matte black, modern composite'],
        ['HOLOGRAM',  'holographic iridescent surface, diffraction rainbow'],
        ['PLASMA',    'electric plasma energy field, glowing discharge'],
        ['VOID',      'void abyss dark space, distant stars, cosmos'],
        ['ALIEN',     'alien bioluminescent surface, organic sci-fi carapace'],
        ['BIO-MECH',  'biomechanical alien surface, organic tech xenomorph'],
      ],
    },
    {
      label: 'SPECIAL',
      color: '#00E5FF',
      prompts: [
        ['WATER',     'deep ocean water, caustics, ripples, blue'],
        ['ICE',       'frozen ice, cracks and translucency, cold blue'],
        ['SNOW',      'snow, white powdery surface, soft texture'],
        ['FROST',     'frost crystal pattern, ice crystal, cold'],
        ['DIAMOND',   'diamond facets, crystal gem, sparkle and dispersion'],
        ['LAVA',      'lava flow, molten magma, glowing crust'],
        ['CERAMIC',   'white ceramic tile, glazed porcelain, clean'],
        ['TERRACOTTA','terracotta pottery, reddish clay, earthy'],
      ],
    },
    {
      label: 'SURFACE',
      color: '#FF9F0A',
      prompts: [
        ['RUBBER',    'black rubber, matte tyre texture, grip pattern'],
        ['PLASTIC',   'grey plastic, smooth resin, industrial'],
        ['PAINT',     'red spray paint, graffiti, rough pigment'],
        ['CHALK',     'chalk matte white paint, rough plaster surface'],
        ['STUCCO',    'mediterranean stucco render, warm pink plaster'],
        ['PLASTER',   'white plaster wall, rough render coat'],
      ],
    },
  ]

  const [activeGroup, setActiveGroup] = React.useState(0)

  return (
    <div style={{ padding: 10 }}>
      <Section label="TEXTURE_PROMPT">
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          rows={3}
          style={{
            width: '100%',
            background: 'var(--gf-bg-3)',
            border: '1px solid var(--gf-border-h)',
            borderRadius: 'var(--gf-radius-sm)',
            color: 'var(--gf-text)',
            fontSize: 11,
            padding: '7px 8px',
            resize: 'vertical', minHeight: 52,
            fontFamily: 'monospace',
            lineHeight: 1.5,
            boxSizing: 'border-box',
          }}
          placeholder="Describe the material surface…"
        />

        {/* Quick prompt grouped tabs */}
        <div style={{ marginTop: 7 }}>
          {/* Category tabs */}
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 2, marginBottom: 5,
          }}>
            {quickPromptGroups.map((g, i) => (
              <button
                key={g.label}
                onClick={() => setActiveGroup(i)}
                style={{
                  padding: '2px 7px', fontSize: 7,
                  background: activeGroup === i
                    ? `rgba(${g.color === '#39FF14' ? '57,255,20' : g.color === '#00E5FF' ? '0,229,255' : g.color === '#FF9F0A' ? '255,159,10' : g.color === '#C8A96E' ? '200,169,110' : g.color === '#A0A0A8' ? '160,160,168' : g.color === '#7DBF7D' ? '125,191,125' : '160,120,74'},0.18)`
                    : 'transparent',
                  border: `1px solid ${activeGroup === i ? g.color + '80' : 'var(--gf-border-h)'}`,
                  borderRadius: 2,
                  color: activeGroup === i ? g.color : 'var(--gf-text-4)',
                  cursor: 'pointer', fontFamily: 'monospace',
                  letterSpacing: '0.08em', textTransform: 'uppercase',
                  transition: 'all 0.1s',
                  textShadow: activeGroup === i ? `0 0 4px ${g.color}` : 'none',
                }}
              >
                {g.label}
              </button>
            ))}
          </div>

          {/* Chips for active group */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {quickPromptGroups[activeGroup].prompts.map(([label, p]) => {
              const gc = quickPromptGroups[activeGroup].color
              const active = prompt === p
              return (
                <button key={label} onClick={() => setPrompt(p)} style={{
                  padding: '2px 7px', fontSize: 8,
                  background: active ? `${gc}22` : 'var(--gf-bg-3)',
                  border: `1px solid ${active ? gc + '80' : 'var(--gf-border-h)'}`,
                  borderRadius: 2,
                  color: active ? gc : 'var(--gf-text-3)',
                  cursor: 'pointer', fontFamily: 'monospace',
                  letterSpacing: '0.07em', textTransform: 'uppercase',
                  transition: 'all 0.1s',
                  boxShadow: active ? `0 0 5px ${gc}30` : 'none',
                  textShadow: active ? `0 0 4px ${gc}` : 'none',
                }}>
                  {label}
                </button>
              )
            })}
          </div>
        </div>
      </Section>

      <Section label="REFERENCE_IMAGE">
        <div
          onClick={() => refInput.current?.click()}
          style={{
            border: `1px dashed ${refFile ? 'var(--gf-neon-dim)' : 'var(--gf-border-h)'}`,
            borderRadius: 'var(--gf-radius-sm)',
            padding: '10px 12px', textAlign: 'center',
            cursor: 'pointer',
            background: refFile ? 'rgba(57,255,20,0.04)' : 'var(--gf-bg-2)',
            boxShadow: refFile ? '0 0 8px #39FF1418' : 'none',
            fontSize: 9, color: refFile ? 'var(--gf-neon-dim)' : 'var(--gf-text-3)',
            fontFamily: 'monospace', letterSpacing: '0.08em',
            textTransform: 'uppercase', transition: 'all 0.12s',
          }}
        >
          {refFile ? `> ${refFile.name}` : '> SELECT_REFERENCE_IMAGE'}
        </div>
        <input ref={refInput} type="file" accept="image/*" hidden
               onChange={e => setRefFile(e.target.files[0] || null)} />
      </Section>

      <Section label="SETTINGS">
        <FieldRow label="TEXTURE_SIZE">
          <select value={texSize} onChange={e => setTexSize(+e.target.value)} style={matrixSelect}>
            <option value={512}>512 px</option>
            <option value={1024}>1024 px</option>
            <option value={2048}>2048 px</option>
          </select>
        </FieldRow>

        <FieldRow label="AI_MODE">
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <MatrixToggle checked={useAI} onChange={setUseAI} />
            <span style={{
              fontSize: 9, color: useAI ? 'var(--gf-neon)' : 'var(--gf-text-3)',
              fontFamily: 'monospace', letterSpacing: '0.08em',
              textShadow: useAI ? '0 0 5px var(--gf-neon)' : 'none',
            }}>
              {useAI ? 'STABLE_DIFFUSION' : 'PROCEDURAL (FAST)'}
            </span>
          </div>
        </FieldRow>

        {useAI && (
          <FieldRow label={`DIFFUSION_STEPS: ${aiSteps}`}>
            <input
              type="range" min={10} max={50} value={aiSteps}
              onChange={e => setAiSteps(+e.target.value)}
              style={{ width: '100%' }}
            />
          </FieldRow>
        )}
      </Section>

      <MatrixActionBtn
        onClick={handleGenerate}
        disabled={running || !selected.file}
        loading={running}
        label="GENERATE_TEXTURE"
      />

      {progress && (
        <div style={{ marginTop: 10 }}>
          <ProgressBar stage={progress.stage} pct={progress.progress} />
        </div>
      )}

      {texPreview && (
        <div style={{ marginTop: 14 }}>
          <Section label="GENERATED_TEXTURE">
            <div style={{
              border: '1px solid var(--gf-neon-dim)',
              borderRadius: 'var(--gf-radius-sm)',
              overflow: 'hidden',
              boxShadow: '0 0 10px #39FF1420',
            }}>
              <img src={texPreview} style={{ width: '100%', display: 'block' }} alt="Texture" />
            </div>
            <div style={{
              marginTop: 5, padding: '4px 7px',
              background: 'rgba(57,255,20,0.04)',
              border: '1px solid var(--gf-border)',
              borderRadius: 2, fontSize: 8,
              color: 'var(--gf-text-3)', fontFamily: 'monospace',
              letterSpacing: '0.06em',
            }}>
              // {prompt}
            </div>
          </Section>

          {/* Download outputs */}
          {doneJobId && (
            <JobOutputPanel jobId={doneJobId} hasTexture={true} />
          )}
        </div>
      )}
    </div>
  )
}

// ─── Audit Tab (P10) ─────────────────────────────────────────────────────────
//
// Reads the asset directory off the selected scene object (set when the
// FORGE pipeline finishes a stage) and runs the audit at the requested
// preset. The audit tab is the user's primary lens onto game-readiness:
// every issue is grouped by category and severity so they can fix it
// before the engine handoff gate slams shut.
// ─── Modifiers Tab (P11) ─────────────────────────────────────────────────────
//
// Non-destructive modifier stack — Blender-modifier semantics translated
// into a graph of OperationNodes the backend evaluates. The user can:
//   * Pick or create an edit graph
//   * Add ops from the palette (refreshOperations)
//   * Reorder, toggle, edit per-op params, remove
//   * Evaluate the graph and view the per-step report
//
// State is mediated entirely through `useAuthoringStore`; this component
// is a pure rendering of that state plus a few action callbacks.
function ModifiersTab({ selected }) {
  const {
    operations, summaries, active, loadingOps, loadingGraph, evaluating, error,
    refreshOperations, refreshGraphs, open, create, remove, appendNode,
    updateNode, removeNode, reorderNodes, evaluate,
  } = useAuthoringStore()
  const [paletteKind, setPaletteKind] = useState('transform')
  const [paramsDraft, setParamsDraft] = useState('{}')
  const [outputPath, setOutputPath] = useState('')

  useEffect(() => { refreshOperations() }, [refreshOperations])
  useEffect(() => { refreshGraphs() }, [refreshGraphs])

  const graph = active?.graph || null
  const evalReport = active?.evaluation || null

  const handleCreate = async () => {
    try {
      await create({
        name: selected?.name || 'modifier-stack',
        base_asset_path: selected?.assetPath || null,
      })
    } catch (_) { /* error already in store */ }
  }

  const handleAppend = async () => {
    if (!graph) return
    let params = {}
    try { params = JSON.parse(paramsDraft || '{}') }
    catch { return }
    try {
      await appendNode(graph.graph_id, { kind: paletteKind, params })
      setParamsDraft('{}')
    } catch (_) { /* swallow — store has error */ }
  }

  const handleEvaluate = async () => {
    if (!graph) return
    const opts = outputPath.trim() ? { output_path: outputPath.trim() } : {}
    try { await evaluate(graph.graph_id, opts) } catch (_) {}
  }

  const swap = async (idx, delta) => {
    if (!graph) return
    const nodes = graph.nodes
    const j = idx + delta
    if (j < 0 || j >= nodes.length) return
    const order = nodes.map(n => n.id)
    ;[order[idx], order[j]] = [order[j], order[idx]]
    try { await reorderNodes(graph.graph_id, order) } catch (_) {}
  }

  return (
    <div style={{ padding: 10 }}>
      <Section label="MODIFIER_STACK">
        <FieldRow label="GRAPH">
          <div style={{ display: 'flex', gap: 4 }}>
            <select
              value={graph?.graph_id || ''}
              onChange={e => e.target.value && open(e.target.value)}
              style={{ ...inputStyle(), flex: 1 }}>
              <option value="">— select graph —</option>
              {summaries.map(g => (
                <option key={g.graph_id} value={g.graph_id}>
                  {g.name || g.graph_id}
                </option>
              ))}
            </select>
            <button onClick={handleCreate} style={smallBtnStyle()} title="Create new graph">
              + NEW
            </button>
          </div>
        </FieldRow>

        {graph && (
          <div style={{
            fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
            margin: '4px 0 8px',
          }}>
            ID: {graph.graph_id} · v{graph.version} · {graph.nodes.length} ops
            <button
              onClick={() => remove(graph.graph_id)}
              style={{ ...smallBtnStyle(), marginLeft: 6, color: 'var(--gf-danger)' }}>
              DEL
            </button>
            {selected && (
              <button
                onClick={() => useSceneStore.getState().bindGraphToObject(selected.id, graph.graph_id)}
                style={{ ...smallBtnStyle(), marginLeft: 6 }}
                title="Bind this graph to the selected scene object so viewport gizmos write into it">
                {selected.graphId === graph.graph_id ? 'BOUND ✓' : 'BIND_TO_SCENE'}
              </button>
            )}
          </div>
        )}
      </Section>

      {graph && (
        <Section label="ADD_NODE">
          <FieldRow label="OPERATION">
            <select
              value={paletteKind}
              onChange={e => setPaletteKind(e.target.value)}
              disabled={loadingOps || operations.length === 0}
              style={inputStyle()}>
              {operations.map(op => (
                <option key={op.kind} value={op.kind}>
                  [{op.category}] {op.label}
                </option>
              ))}
            </select>
          </FieldRow>
          <FieldRow label="PARAMS_JSON">
            <textarea
              value={paramsDraft}
              onChange={e => setParamsDraft(e.target.value)}
              rows={3}
              style={{ ...inputStyle(), height: 'auto', resize: 'vertical', fontFamily: 'monospace' }}
              placeholder={'{}'}
            />
          </FieldRow>
          <button onClick={handleAppend} style={runButtonStyle(false)}>
            + APPEND_NODE
          </button>
        </Section>
      )}

      {graph && graph.nodes.length > 0 && (
        <Section label="STACK">
          {graph.nodes.map((node, idx) => (
            <NodeRow
              key={node.id}
              index={idx}
              node={node}
              onMoveUp={() => swap(idx, -1)}
              onMoveDown={() => swap(idx, +1)}
              onToggle={() => updateNode(graph.graph_id, node.id, { enabled: !node.enabled })}
              onDelete={() => removeNode(graph.graph_id, node.id)}
              onRename={(label) => updateNode(graph.graph_id, node.id, { label })}
              onParams={(p) => updateNode(graph.graph_id, node.id, { params: p })}
              evaluation={evalReport?.steps?.find(s => s.node_id === node.id) || null}
            />
          ))}
        </Section>
      )}

      {graph && (
        <Section label="EVALUATE">
          <FieldRow label="OUTPUT_PATH (optional)">
            <input
              value={outputPath}
              onChange={e => setOutputPath(e.target.value)}
              placeholder={graph.output_path || 'data/assets/<id>/preview.glb'}
              style={inputStyle()}
            />
          </FieldRow>
          <button
            onClick={handleEvaluate}
            disabled={evaluating || !graph.base_asset_path}
            style={runButtonStyle(evaluating)}>
            {evaluating ? '> EVALUATING…' : '> EVALUATE_GRAPH'}
          </button>
          {!graph.base_asset_path && (
            <div style={{
              fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
              marginTop: 6, fontStyle: 'italic',
            }}>
              base_asset_path is empty. Set it via the API or pick an asset
              in the scene before creating the graph.
            </div>
          )}
        </Section>
      )}

      {evalReport && (
        <Section label="LAST_EVALUATION">
          <div style={{
            padding: '6px 8px', borderRadius: 'var(--gf-radius-sm)',
            border: '1px solid var(--gf-border)',
            background: evalReport.status === 'succeeded'
              ? 'rgba(57,255,20,0.05)' : 'rgba(255,45,85,0.05)',
          }}>
            <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--gf-text-2)' }}>
              status: <strong style={{
                color: evalReport.status === 'succeeded'
                  ? 'var(--gf-neon)' : 'var(--gf-danger)',
              }}>{evalReport.status}</strong>
            </div>
            <div style={{ fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace' }}>
              steps: {evalReport.steps.length} · {evalReport.duration_ms.toFixed(0)} ms
            </div>
            {evalReport.output_path && (
              <div style={{ fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace', marginTop: 3 }}>
                {evalReport.output_path}
              </div>
            )}
          </div>
        </Section>
      )}

      {error && <ErrorBox message={error} />}
    </div>
  )
}

function NodeRow({ index, node, onMoveUp, onMoveDown, onToggle, onDelete, onRename, onParams, evaluation }) {
  const [editing, setEditing] = useState(false)
  const [labelDraft, setLabelDraft] = useState(node.label || '')
  const [paramsDraft, setParamsDraft] = useState(JSON.stringify(node.params || {}, null, 2))

  const stepColor = evaluation
    ? evaluation.status === 'succeeded' ? 'var(--gf-neon)'
    : evaluation.status === 'failed' ? 'var(--gf-danger)'
    : 'var(--gf-text-3)'
    : 'var(--gf-border)'

  return (
    <div style={{
      border: `1px solid ${stepColor}`, marginBottom: 6,
      padding: '6px 8px', borderRadius: 'var(--gf-radius-sm)',
      background: node.enabled ? 'var(--gf-bg-2)' : 'rgba(255,255,255,0.02)',
      opacity: node.enabled ? 1 : 0.55,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{
          fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
          minWidth: 16,
        }}>{String(index + 1).padStart(2, '0')}</span>
        <span style={{
          flex: 1, fontSize: 11, fontFamily: 'monospace',
          color: 'var(--gf-text-1)',
        }}>
          {node.label || node.kind}
          <span style={{ color: 'var(--gf-text-3)', marginLeft: 4, fontSize: 9 }}>
            ({node.kind})
          </span>
        </span>
        <button onClick={onToggle} style={miniBtnStyle()} title="Toggle enabled">
          {node.enabled ? 'ON' : 'OFF'}
        </button>
        <button onClick={onMoveUp} style={miniBtnStyle()} title="Move up">↑</button>
        <button onClick={onMoveDown} style={miniBtnStyle()} title="Move down">↓</button>
        <button onClick={() => setEditing(v => !v)} style={miniBtnStyle()} title="Edit">
          {editing ? '✕' : '⚙'}
        </button>
        <button onClick={onDelete} style={{ ...miniBtnStyle(), color: 'var(--gf-danger)' }} title="Delete">
          DEL
        </button>
      </div>
      {evaluation && (
        <div style={{
          fontSize: 8, color: 'var(--gf-text-3)', marginTop: 4, fontFamily: 'monospace',
        }}>
          {evaluation.status} · {evaluation.duration_ms.toFixed(1)} ms
          {evaluation.error && (
            <span style={{ color: 'var(--gf-danger)', marginLeft: 6 }}>
              {evaluation.error}
            </span>
          )}
          {evaluation.message && !evaluation.error && (
            <span style={{ marginLeft: 6 }}>{evaluation.message}</span>
          )}
        </div>
      )}
      {editing && (
        <div style={{ marginTop: 6 }}>
          <FieldRow label="LABEL">
            <input
              value={labelDraft}
              onChange={e => setLabelDraft(e.target.value)}
              onBlur={() => onRename(labelDraft)}
              style={inputStyle()}
            />
          </FieldRow>
          <FieldRow label="PARAMS_JSON">
            <textarea
              value={paramsDraft}
              onChange={e => setParamsDraft(e.target.value)}
              onBlur={() => {
                try { onParams(JSON.parse(paramsDraft || '{}')) }
                catch { /* keep draft, user fixes manually */ }
              }}
              rows={4}
              style={{ ...inputStyle(), height: 'auto', resize: 'vertical' }}
            />
          </FieldRow>
        </div>
      )}
    </div>
  )
}

function smallBtnStyle() {
  return {
    height: 22, padding: '0 8px',
    background: 'var(--gf-bg-3)',
    border: '1px solid var(--gf-border)',
    borderRadius: 'var(--gf-radius-sm)',
    color: 'var(--gf-text-2)',
    fontSize: 9, fontFamily: 'monospace', cursor: 'pointer',
    whiteSpace: 'nowrap',
  }
}

function miniBtnStyle() {
  return {
    height: 18, padding: '0 5px',
    background: 'var(--gf-bg-3)',
    border: '1px solid var(--gf-border)',
    borderRadius: 'var(--gf-radius-sm)',
    color: 'var(--gf-text-2)',
    fontSize: 8, fontFamily: 'monospace', cursor: 'pointer',
  }
}

// ─── Audit Tab ────────────────────────────────────────────────────────────────
function AuditTab({ selected }) {
  const { presets, lastReport, lastAssetDir, loading, error, loadPresets, run, clear } =
    useAuditStore()
  const [preset, setPreset] = useState('default')
  const [runGltf, setRunGltf] = useState(false)
  const [assetDirOverride, setAssetDirOverride] = useState('')

  useEffect(() => { loadPresets() }, [loadPresets])

  // Prefer asset-dir saved on the scene object (set by the slice
  // executor); otherwise fall back to a manual override field so the
  // user can audit any folder on disk without hunting through scene
  // state.
  const targetDir = selected?.assetDir || assetDirOverride.trim()

  const handleRun = async () => {
    if (!targetDir) return
    try { await run({ assetDir: targetDir, preset, runGltfValidator: runGltf }) }
    catch (_) { /* error already in store */ }
  }

  return (
    <div style={{ padding: 10 }}>
      <Section label="GAME_READINESS_AUDIT">
        <FieldRow label="ASSET_DIR">
          <input
            value={selected?.assetDir || assetDirOverride}
            onChange={e => setAssetDirOverride(e.target.value)}
            disabled={!!selected?.assetDir}
            placeholder="data/assets/<asset_id>"
            style={inputStyle()}
          />
        </FieldRow>

        <FieldRow label="PRESET">
          <div style={{ display: 'flex', gap: 3 }}>
            {['default', 'unity', 'unreal'].map(p => (
              <button key={p} onClick={() => setPreset(p)} style={{
                flex: 1, height: 22,
                background: preset === p ? 'rgba(57,255,20,0.1)' : 'var(--gf-bg-3)',
                border: `1px solid ${preset === p ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
                color: preset === p ? 'var(--gf-neon)' : 'var(--gf-text-3)',
                fontSize: 9, fontFamily: 'monospace', cursor: 'pointer',
                borderRadius: 'var(--gf-radius-sm)',
              }}>{p.toUpperCase()}</button>
            ))}
          </div>
        </FieldRow>

        <label style={{ display: 'flex', alignItems: 'center', gap: 6,
                        fontSize: 9, color: 'var(--gf-text-3)',
                        fontFamily: 'monospace', margin: '6px 0 8px' }}>
          <input type="checkbox" checked={runGltf} onChange={e => setRunGltf(e.target.checked)} />
          RUN_GLTF_VALIDATOR
        </label>

        <button onClick={handleRun} disabled={!targetDir || loading} style={runButtonStyle(loading)}>
          {loading ? '> AUDITING…' : '> RUN_AUDIT'}
        </button>

        {error && <ErrorBox message={error} />}
      </Section>

      {lastReport && lastAssetDir === targetDir && (
        <AuditReportView report={lastReport} onClear={clear} />
      )}

      <RetargetPanel targetDir={targetDir} />
    </div>
  )
}

// ─── Retarget Panel (P12) ────────────────────────────────────────────────────
//
// Lives inside the AUDIT tab. Shows the cross-engine readiness for a
// chosen target engine and offers a one-shot AUTO-RETARGET button that
// asks the planner to build an EditGraph (P11) of retarget operations.
// The graph is persisted, so the user can switch to the MODS tab and
// see it fully populated.
function RetargetPanel({ targetDir }) {
  const {
    profiles, lastReport, lastGraph, planning, loading, error,
    refreshProfiles, lint, plan, clear,
  } = useRetargetStore()
  const [target, setTarget] = useState('unreal')
  const [baseName, setBaseName] = useState('')
  const { setRightTab } = useUIStore()

  useEffect(() => { refreshProfiles() }, [refreshProfiles])

  const targetableProfiles = profiles.filter(p => p.name !== 'gltf_canonical')

  const handleLint = async () => {
    if (!targetDir) return
    try { await lint({ assetDir: targetDir, targetEngine: target }) }
    catch (_) { /* in store */ }
  }

  const handlePlan = async () => {
    if (!targetDir) return
    try {
      await plan({
        assetDir: targetDir,
        targetEngine: target,
        baseName: baseName.trim() || null,
        persistGraph: true,
      })
    } catch (_) { /* in store */ }
  }

  // Pull only retarget.* issues from the lint report; the same call
  // also surfaces general audit issues but those already render in
  // AuditReportView above.
  const retargetIssues =
    (lastReport?.issues || []).filter(i => (i.rule || '').startsWith('retarget.'))

  return (
    <Section label="CROSS_ENGINE_RETARGET">
      <FieldRow label="TARGET_ENGINE">
        <div style={{ display: 'flex', gap: 3 }}>
          {targetableProfiles.map(p => (
            <button
              key={p.name}
              onClick={() => setTarget(p.name)}
              style={{
                flex: 1, height: 22,
                background: target === p.name ? 'rgba(57,255,20,0.1)' : 'var(--gf-bg-3)',
                border: `1px solid ${target === p.name ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
                color: target === p.name ? 'var(--gf-neon)' : 'var(--gf-text-3)',
                fontSize: 9, fontFamily: 'monospace', cursor: 'pointer',
                borderRadius: 'var(--gf-radius-sm)',
              }}>
              {p.label.toUpperCase()}
            </button>
          ))}
          {targetableProfiles.length === 0 && (
            <span style={{ fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace' }}>
              loading profiles…
            </span>
          )}
        </div>
      </FieldRow>

      <FieldRow label="BASE_NAME (optional)">
        <input
          value={baseName}
          onChange={e => setBaseName(e.target.value)}
          placeholder="HeroProp"
          style={inputStyle()}
        />
      </FieldRow>

      <div style={{ display: 'flex', gap: 4 }}>
        <button
          onClick={handleLint}
          disabled={!targetDir || loading}
          style={{ ...runButtonStyle(loading), flex: 1 }}>
          {loading ? '> LINTING…' : '> LINT'}
        </button>
        <button
          onClick={handlePlan}
          disabled={!targetDir || planning}
          style={{ ...runButtonStyle(planning), flex: 1 }}>
          {planning ? '> PLANNING…' : '> AUTO_RETARGET'}
        </button>
      </div>

      {error && <ErrorBox message={error} />}

      {retargetIssues.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={{
            fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
            marginBottom: 4, letterSpacing: '0.1em',
          }}>// RETARGET_DIAGNOSTICS</div>
          {retargetIssues.map((issue, i) => (
            <div key={`${issue.rule}-${i}`} style={{
              padding: '4px 6px', marginBottom: 2,
              background: 'var(--gf-bg-3)',
              borderLeft: `2px solid ${
                issue.severity === 'error' ? 'var(--gf-danger)'
                : issue.severity === 'warning' ? 'var(--gf-cyan)'
                : 'var(--gf-neon-dim)'
              }`,
              borderRadius: 'var(--gf-radius-sm)',
            }}>
              <div style={{
                fontSize: 9, color: 'var(--gf-text-2)', fontFamily: 'monospace',
              }}>{issue.code}</div>
              <div style={{ fontSize: 9, color: 'var(--gf-text-3)' }}>
                {issue.message}
              </div>
            </div>
          ))}
        </div>
      )}

      {lastGraph && (
        <div style={{
          marginTop: 8, padding: '6px 8px',
          border: '1px solid var(--gf-neon-dim)',
          borderRadius: 'var(--gf-radius-sm)',
          background: 'rgba(57,255,20,0.05)',
        }}>
          <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--gf-neon)' }}>
            graph: {lastGraph.graph_id}
          </div>
          <div style={{ fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace' }}>
            {lastGraph.nodes.length} retarget op{lastGraph.nodes.length === 1 ? '' : 's'} planned
          </div>
          <button
            onClick={() => setRightTab('modifiers')}
            style={{ ...smallBtnStyle(), marginTop: 6 }}>
            OPEN_IN_MODS →
          </button>
        </div>
      )}
    </Section>
  )
}

function AuditReportView({ report, onClear }) {
  const status = report.status || (report.errors > 0 ? 'failed' : report.warnings > 0 ? 'warned' : 'passed')
  const statusColor = status === 'passed' ? 'var(--gf-neon)'
    : status === 'warned' ? 'var(--gf-cyan)'
    : 'var(--gf-danger)'

  // Group issues by severity for the UI (matches the audit report
  // schema: issues live on each rule_result).
  const allIssues = (report.rule_results || []).flatMap(r => r.issues || [])
  const errors = allIssues.filter(i => i.severity === 'error')
  const warnings = allIssues.filter(i => i.severity === 'warning')
  const infos = allIssues.filter(i => i.severity === 'info')

  return (
    <Section label="AUDIT_REPORT">
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 0', marginBottom: 6,
        borderBottom: '1px solid var(--gf-border)',
      }}>
        <span style={{
          fontSize: 11, color: statusColor, fontFamily: 'monospace',
          fontWeight: 700, letterSpacing: '0.1em',
          textShadow: status === 'passed' ? '0 0 5px var(--gf-neon)' : 'none',
        }}>
          {status.toUpperCase()}
        </span>
        <button onClick={onClear} style={{
          background: 'none', border: 'none', color: 'var(--gf-text-4)',
          cursor: 'pointer', fontSize: 9, fontFamily: 'monospace',
        }}>CLEAR</button>
      </div>

      <PropRow label="ERRORS"   value={errors.length}
        valueColor={errors.length ? 'var(--gf-danger)' : 'var(--gf-text-3)'} />
      <PropRow label="WARNINGS" value={warnings.length}
        valueColor={warnings.length ? 'var(--gf-cyan)' : 'var(--gf-text-3)'} />
      <PropRow label="INFOS"    value={infos.length} />

      {errors.length > 0 && <IssueList title="ERRORS" issues={errors} color="var(--gf-danger)" />}
      {warnings.length > 0 && <IssueList title="WARNINGS" issues={warnings} color="var(--gf-cyan)" />}
    </Section>
  )
}

function IssueList({ title, issues, color }) {
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{
        fontSize: 8, color, fontFamily: 'monospace',
        letterSpacing: '0.1em', marginBottom: 3,
      }}>// {title}</div>
      {issues.map((issue, i) => (
        <div key={i} style={{
          padding: '4px 6px', marginBottom: 2,
          background: 'var(--gf-bg-3)',
          border: `1px solid ${color}33`,
          borderLeft: `2px solid ${color}`,
          borderRadius: 'var(--gf-radius-sm)',
        }}>
          <div style={{ fontSize: 9, color: 'var(--gf-text-2)',
                        fontFamily: 'monospace', marginBottom: 1 }}>
            {issue.code}
          </div>
          <div style={{ fontSize: 9, color: 'var(--gf-text-3)' }}>
            {issue.message}
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Engine Tab (P10) ─────────────────────────────────────────────────────────
//
// Creates offline bridge packages for Unity / Unreal MCP importers. Direct
// send remains available only when an adapter transport is configured, but
// the primary Ghost-Forge export path is a manifest-backed bridge JSON.
function EngineTab({ selected }) {
  const { adapters, refresh, configure, send, exportBridge, error, loading, handoffs, bridges } =
    useEnginesStore()
  const [activeName, setActiveName] = useState(null)
  const [assetDirOverride, setAssetDirOverride] = useState('')

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    if (!activeName && adapters.length) setActiveName(adapters[0].name)
  }, [adapters, activeName])

  const adapter = adapters.find(a => a.name === activeName) || null
  const targetDir = selected?.assetDir || assetDirOverride.trim()

  return (
    <div style={{ padding: 10 }}>
      <Section label="ENGINE_HANDOFF">
        {/* Adapter selector */}
        <div style={{ display: 'flex', gap: 3, marginBottom: 8 }}>
          {adapters.map(a => (
            <button key={a.name} onClick={() => setActiveName(a.name)} style={{
              flex: 1, height: 24,
              background: activeName === a.name ? 'rgba(57,255,20,0.1)' : 'var(--gf-bg-3)',
              border: `1px solid ${activeName === a.name ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
              color: activeName === a.name ? 'var(--gf-neon)' : 'var(--gf-text-3)',
              fontSize: 9, fontFamily: 'monospace', cursor: 'pointer',
              borderRadius: 'var(--gf-radius-sm)',
              fontWeight: 700, letterSpacing: '0.08em',
            }}>{a.name.toUpperCase()}</button>
          ))}
        </div>

        {adapter ? (
          <EngineAdapterPanel
            adapter={adapter}
            targetDir={targetDir}
            assetDirOverride={assetDirOverride}
            onAssetDirChange={setAssetDirOverride}
            disabled={!!selected?.assetDir}
            onConfigure={(config) => configure(adapter.name, config)}
            onSend={(payload) => send(adapter.name, payload)}
            onExportBridge={(payload) => exportBridge(adapter.name, payload)}
            loading={loading}
          />
        ) : (
          <div style={{ padding: 10, fontSize: 9, color: 'var(--gf-text-4)',
                        fontFamily: 'monospace', textAlign: 'center' }}>
            // NO ADAPTERS REGISTERED
          </div>
        )}

        {error && <ErrorBox message={error} />}
      </Section>

      {handoffs.length > 0 && (
        <Section label="RECENT_HANDOFFS">
          {handoffs.slice(0, 5).map((h, i) => (
            <div key={i} style={{
              padding: '4px 6px', marginBottom: 3,
              background: 'var(--gf-bg-3)',
              border: '1px solid var(--gf-border)',
              borderLeft: '2px solid var(--gf-neon)',
              borderRadius: 'var(--gf-radius-sm)',
            }}>
              <div style={{ fontSize: 9, color: 'var(--gf-neon)', fontFamily: 'monospace',
                            textShadow: '0 0 4px var(--gf-neon)' }}>
                {h.engine.toUpperCase()}
              </div>
              <div style={{ fontSize: 8, color: 'var(--gf-text-3)',
                            fontFamily: 'monospace', overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {h.assetDir}
              </div>
            </div>
          ))}
        </Section>
      )}

      {bridges.length > 0 && (
        <Section label="RECENT_EXPORT_BRIDGES">
          {bridges.slice(0, 5).map((h, i) => (
            <div key={i} style={{
              padding: '4px 6px', marginBottom: 3,
              background: 'var(--gf-bg-3)',
              border: '1px solid var(--gf-border)',
              borderLeft: '2px solid var(--gf-cyan)',
              borderRadius: 'var(--gf-radius-sm)',
            }}>
              <div style={{ fontSize: 9, color: 'var(--gf-cyan)', fontFamily: 'monospace' }}>
                {h.engine.toUpperCase()} BRIDGE
              </div>
              <div style={{ fontSize: 8, color: 'var(--gf-text-3)',
                            fontFamily: 'monospace', overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {h.result?.package_path || h.assetDir}
              </div>
            </div>
          ))}
        </Section>
      )}
    </div>
  )
}

function EngineAdapterPanel({
  adapter, targetDir, assetDirOverride, onAssetDirChange, disabled,
  onConfigure, onSend, onExportBridge, loading,
}) {
  const probe = adapter.probe || {}
  const isConfigured = probe.configured === true
  const transport = probe.transport || 'none'

  // Local form state for configuration. Defaults differ per engine;
  // we read them from the existing probe so re-entering this tab feels
  // continuous.
  const [transportKind, setTransportKind] = useState(transport === 'none' ? 'stdio' : transport)
  const [command, setCommand] = useState((probe.command || []).join(' '))
  const [url, setUrl] = useState(probe.url || '')
  const [audit, setAudit] = useState(true)
  const [auditPreset, setAuditPreset] = useState(adapter.default_audit_preset || 'default')
  const [force, setForce] = useState(false)
  const [dryRun, setDryRun] = useState(false)

  return (
    <div>
      <div style={{
        padding: '5px 8px', marginBottom: 8,
        background: isConfigured ? 'rgba(57,255,20,0.05)' : 'var(--gf-bg-3)',
        border: `1px solid ${isConfigured ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: 9, fontFamily: 'monospace',
                       color: isConfigured ? 'var(--gf-neon)' : 'var(--gf-text-3)',
                       textShadow: isConfigured ? '0 0 4px var(--gf-neon)' : 'none' }}>
          {isConfigured ? `> ${transport.toUpperCase()}_READY` : '> NOT_CONFIGURED'}
        </span>
        <span style={{ fontSize: 8, color: 'var(--gf-text-4)',
                       fontFamily: 'monospace' }}>
          {adapter.default_audit_preset || 'default'}
        </span>
      </div>

      <FieldRow label="TRANSPORT">
        <div style={{ display: 'flex', gap: 3 }}>
          {['stdio', 'http'].map(t => (
            <button key={t} onClick={() => setTransportKind(t)} style={{
              flex: 1, height: 22,
              background: transportKind === t ? 'rgba(57,255,20,0.1)' : 'var(--gf-bg-3)',
              border: `1px solid ${transportKind === t ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
              color: transportKind === t ? 'var(--gf-neon)' : 'var(--gf-text-3)',
              fontSize: 9, fontFamily: 'monospace', cursor: 'pointer',
              borderRadius: 'var(--gf-radius-sm)',
            }}>{t.toUpperCase()}</button>
          ))}
        </div>
      </FieldRow>

      {transportKind === 'stdio' && (
        <FieldRow label="COMMAND">
          <input value={command} onChange={e => setCommand(e.target.value)}
            placeholder="python -m unity_mcp_ghost"
            style={inputStyle()} />
        </FieldRow>
      )}

      {transportKind === 'http' && (
        <FieldRow label="URL">
          <input value={url} onChange={e => setUrl(e.target.value)}
            placeholder="http://localhost:8765"
            style={inputStyle()} />
        </FieldRow>
      )}

      <button
        onClick={() => onConfigure({
          transport: transportKind,
          command: transportKind === 'stdio' ? command.split(/\s+/).filter(Boolean) : [],
          url: transportKind === 'http' ? url : null,
        })}
        style={{
          width: '100%', height: 24, marginBottom: 8,
          background: 'var(--gf-bg-3)',
          border: '1px solid var(--gf-border-h)',
          color: 'var(--gf-text-2)',
          fontSize: 9, fontFamily: 'monospace', fontWeight: 700,
          letterSpacing: '0.08em', cursor: 'pointer',
          borderRadius: 'var(--gf-radius-sm)',
        }}>
        APPLY_CONFIG
      </button>

      <hr style={{ border: 0, borderTop: '1px solid var(--gf-border)', margin: '8px 0' }} />

      <FieldRow label="ASSET_DIR">
        <input
          value={targetDir}
          onChange={e => onAssetDirChange(e.target.value)}
          disabled={disabled}
          placeholder="data/assets/<asset_id>"
          style={inputStyle()}
        />
      </FieldRow>

      <FieldRow label="AUDIT_GATE">
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <input type="checkbox" checked={audit} onChange={e => setAudit(e.target.checked)} />
          <select value={auditPreset} onChange={e => setAuditPreset(e.target.value)}
            disabled={!audit}
            style={{
              flex: 1, height: 22, background: 'var(--gf-bg-3)',
              border: '1px solid var(--gf-border)', color: 'var(--gf-text-2)',
              fontSize: 9, fontFamily: 'monospace',
              borderRadius: 'var(--gf-radius-sm)', padding: '0 4px',
            }}>
            <option value="default">DEFAULT</option>
            <option value="unity">UNITY</option>
            <option value="unreal">UNREAL</option>
          </select>
        </div>
      </FieldRow>

      <label style={{ display: 'flex', alignItems: 'center', gap: 6,
                      fontSize: 9, color: 'var(--gf-text-3)',
                      fontFamily: 'monospace', margin: '4px 0' }}>
        <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
        FORCE (skip audit gate)
      </label>

      <label style={{ display: 'flex', alignItems: 'center', gap: 6,
                      fontSize: 9, color: 'var(--gf-text-3)',
                      fontFamily: 'monospace', margin: '0 0 8px' }}>
        <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} />
        DRY_RUN
      </label>

      <button
        disabled={loading || !targetDir}
        onClick={() => onExportBridge({
          asset_dir: targetDir,
          recommended_tool: 'import_asset',
        })}
        style={{ ...runButtonStyle(loading), borderColor: 'var(--gf-cyan)', color: 'var(--gf-cyan)' }}>
        {loading ? '> EXPORTING…' : '> EXPORT_BRIDGE_JSON'}
      </button>

      <div style={{
        fontSize: 8, color: 'var(--gf-text-4)', fontFamily: 'monospace',
        lineHeight: 1.6, margin: '5px 0 8px',
      }}>
        // Preferred path: write bridge JSON, then import through Unity/Unreal MCP.
      </div>

      <button
        disabled={loading || !isConfigured || !targetDir}
        onClick={() => onSend({
          asset_dir: targetDir,
          audit, audit_preset: auditPreset, force, dry_run: dryRun,
        })}
        style={runButtonStyle(loading)}>
        {loading ? '> SENDING…' : '> SEND_TO_ENGINE'}
      </button>
    </div>
  )
}

// ─── Shared sub-components for new tabs ───────────────────────────────────────

function inputStyle() {
  return {
    width: '100%', height: 22, padding: '0 6px',
    background: 'var(--gf-bg-3)',
    border: '1px solid var(--gf-border)',
    borderRadius: 'var(--gf-radius-sm)',
    color: 'var(--gf-text-2)',
    fontSize: 10, fontFamily: 'monospace',
    outline: 'none',
  }
}

function runButtonStyle(loading) {
  return {
    width: '100%', height: 28, marginTop: 4,
    background: loading ? 'var(--gf-bg-3)' : 'rgba(57,255,20,0.1)',
    border: '1px solid var(--gf-neon-dim)',
    borderRadius: 'var(--gf-radius-sm)',
    color: 'var(--gf-neon)',
    fontSize: 9, fontFamily: 'monospace', fontWeight: 700,
    letterSpacing: '0.12em', cursor: loading ? 'wait' : 'pointer',
    textShadow: '0 0 5px var(--gf-neon)',
  }
}

function ErrorBox({ message }) {
  return (
    <div style={{
      marginTop: 8, padding: '5px 8px',
      background: 'rgba(255,45,85,0.05)',
      border: '1px solid rgba(255,45,85,0.25)',
      borderRadius: 'var(--gf-radius-sm)',
      fontSize: 9, color: 'var(--gf-danger)',
      fontFamily: 'monospace',
    }}>{message}</div>
  )
}
