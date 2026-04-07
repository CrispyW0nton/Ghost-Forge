import React, { useState } from 'react'
import { useUIStore, useSceneStore, useSettingsStore } from '../store'
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
        <TabBtn label="TEXTURE" active={activeRightTab === 'texture'}    onClick={() => setRightTab('texture')} />
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {activeRightTab === 'properties' && <PropertiesTab selected={selected} />}
        {activeRightTab === 'uv'         && <UVTab         selected={selected} />}
        {activeRightTab === 'texture'    && <TextureTab    selected={selected} />}
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
