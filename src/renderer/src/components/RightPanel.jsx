import React, { useState } from 'react'
import { useUIStore, useSceneStore, useSettingsStore } from '../store'
import { createUVTextureJob, pollJob, getPreviewUrl } from '../modules/api'

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

function MatrixActionBtn({ onClick, disabled, loading, label }) {
  const [hover, setHover] = useState(false)
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: '100%', height: 32,
        background: disabled ? 'transparent'
          : hover ? 'rgba(57,255,20,0.18)' : 'rgba(57,255,20,0.09)',
        border: `1px solid ${disabled ? 'var(--gf-border)' : hover ? 'var(--gf-neon)' : 'var(--gf-neon-dim)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        color: disabled ? 'var(--gf-text-4)' : 'var(--gf-neon)',
        fontSize: 9, fontWeight: 700, fontFamily: 'monospace',
        letterSpacing: '0.15em', textTransform: 'uppercase',
        cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        transition: 'all 0.1s',
        boxShadow: disabled ? 'none' : hover
          ? '0 0 14px #39FF1440, inset 0 0 8px #39FF1408'
          : '0 0 6px #39FF1420',
        textShadow: disabled ? 'none' : '0 0 6px var(--gf-neon)',
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
    </div>
  )
}

// ─── UV Tab ──────────────────────────────────────────────────────────────────
function UVTab({ selected }) {
  const [atlasSize, setAtlasSize] = useState(1024)
  const [padding, setPadding]     = useState(2)
  const [running, setRunning]     = useState(false)
  const [progress, setProgress]   = useState(null)
  const [uvPreview, setUvPreview] = useState(null)
  const { updateObject, setActiveJob, clearActiveJob } = useSceneStore()

  if (!selected) return <Empty msg="Select an object to unwrap UVs" />

  const handleUnwrap = async () => {
    if (!selected.file) return
    setRunning(true)
    setProgress({ stage: 'INITIALISING', progress: 0 })

    try {
      const job = await createUVTextureJob({
        meshFile: selected.file,
        prompt: 'placeholder',
        textureSize: atlasSize,
        outputFormat: 'glb',
      })
      setActiveJob({ id: job.job_id, type: 'UV_UNWRAP', status: 'running', progress: 0, stage: 'STARTING' })

      pollJob(
        job.job_id,
        (j) => { setProgress(j); setActiveJob({ id: j.id, type: 'UV_UNWRAP', ...j }) },
        (j) => {
          setRunning(false); setProgress(j); clearActiveJob()
          setUvPreview(getPreviewUrl(j.id, 'uv_layout'))
          updateObject(selected.id, { uvDone: true, jobId: j.id })
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
      </Section>

      <div style={{
        padding: '6px 8px', marginBottom: 10,
        background: 'rgba(0,229,255,0.04)',
        border: '1px solid rgba(0,229,255,0.15)',
        borderRadius: 'var(--gf-radius-sm)',
        fontSize: 9, color: 'var(--gf-cyan-dim)',
        fontFamily: 'monospace', letterSpacing: '0.06em',
        lineHeight: 1.7,
      }}>
        // Algorithm: xatlas ABF++<br/>
        // Pro-grade UV unwrapping engine
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
  const refInput = React.useRef()
  const { updateObject, setActiveJob, clearActiveJob } = useSceneStore()

  if (!selected) return <Empty msg="Select an object to generate textures" />

  const handleGenerate = async () => {
    if (!selected.file) return
    setRunning(true)
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
          setRunning(false); setProgress(j); clearActiveJob()
          setTexPreview(getPreviewUrl(j.id, 'texture'))
          updateObject(selected.id, { textureDone: true, texturePrompt: prompt, jobId: j.id })
        },
        (err) => { setRunning(false); setProgress({ stage: `ERR: ${err.message}`, progress: 0 }); clearActiveJob() }
      )
    } catch (e) {
      setRunning(false)
      setProgress({ stage: `ERR: ${e.message}`, progress: 0 })
    }
  }

  const quickPrompts = [
    ['RUST', 'rusted iron, oxidised, worn metal'],
    ['MARBLE', 'polished marble, white veins, luxury'],
    ['WOOD', 'aged oak wood grain, natural'],
    ['CONCRETE', 'raw concrete, grey, brutalist'],
    ['LEATHER', 'dark leather, stitched, worn'],
    ['GOLD', 'polished gold, metallic, reflective'],
    ['MATRIX', 'dark circuit board, green neon, cyberpunk'],
    ['STONE', 'ancient stone, cracked, mossy'],
  ]

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
          }}
          placeholder="Describe the material surface…"
        />

        {/* Quick prompt chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 6 }}>
          {quickPrompts.map(([label, p]) => (
            <button key={label} onClick={() => setPrompt(p)} style={{
              padding: '2px 7px', fontSize: 8,
              background: prompt === p ? 'rgba(57,255,20,0.12)' : 'var(--gf-bg-3)',
              border: `1px solid ${prompt === p ? 'var(--gf-neon-dim)' : 'var(--gf-border-h)'}`,
              borderRadius: 2,
              color: prompt === p ? 'var(--gf-neon)' : 'var(--gf-text-3)',
              cursor: 'pointer', fontFamily: 'monospace',
              letterSpacing: '0.08em', textTransform: 'uppercase',
              transition: 'all 0.1s',
              boxShadow: prompt === p ? '0 0 5px #39FF1430' : 'none',
              textShadow: prompt === p ? '0 0 4px var(--gf-neon)' : 'none',
            }}>
              {label}
            </button>
          ))}
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
            <option value={512}>512</option>
            <option value={1024}>1024</option>
            <option value={2048}>2048</option>
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
        </div>
      )}
    </div>
  )
}
