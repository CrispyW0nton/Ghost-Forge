import React, { useState } from 'react'
import { useUIStore, useSceneStore, useSettingsStore } from '../store'
import { createUVTextureJob, pollJob, getPreviewUrl } from '../modules/api'

export default function RightPanel() {
  const { activeRightTab, setRightTab } = useUIStore()
  const { selectedIds, objects } = useSceneStore()
  const selected = objects.find(o => selectedIds.includes(o.id)) || null

  return (
    <div style={{
      width: 'var(--right-panel-w)',
      background: 'var(--gf-bg-1)',
      borderLeft: '1px solid var(--gf-border)',
      display: 'flex', flexDirection: 'column',
      flexShrink: 0, overflow: 'hidden',
    }}>
      {/* Tabs */}
      <div className="flex" style={{ borderBottom: '1px solid var(--gf-border)', flexShrink: 0 }}>
        {['properties', 'uv', 'texture'].map(tab => (
          <button key={tab} onClick={() => setRightTab(tab)} style={{
            flex: 1, height: 34,
            background: activeRightTab === tab ? 'var(--gf-bg-2)' : 'transparent',
            border: 'none',
            borderBottom: activeRightTab === tab ? '2px solid var(--gf-forge)' : '2px solid transparent',
            color: activeRightTab === tab ? 'var(--gf-text)' : 'var(--gf-text-3)',
            fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px',
            cursor: 'pointer', transition: 'all 0.15s',
          }}>
            {tab === 'properties' ? 'Props' : tab === 'uv' ? 'UV' : 'Texture'}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {activeRightTab === 'properties' && <PropertiesTab selected={selected} />}
        {activeRightTab === 'uv'         && <UVTab selected={selected} />}
        {activeRightTab === 'texture'    && <TextureTab selected={selected} />}
      </div>
    </div>
  )
}

// ─── Properties ───────────────────────────────────────────────────────────────
function PropertiesTab({ selected }) {
  if (!selected) return <Empty msg="Select an object to view properties" />

  return (
    <div style={{ padding: 10 }}>
      <Section label="Object">
        <PropRow label="Name"  value={selected.name} />
        <PropRow label="Type"  value={selected.type || 'Mesh'} />
        <PropRow label="UV"    value={selected.uvDone ? '✓ Unwrapped' : '✗ None'} valueColor={selected.uvDone ? 'var(--gf-success)' : 'var(--gf-text-3)'} />
        <PropRow label="Texture" value={selected.textureDone ? '✓ Applied' : '✗ None'} valueColor={selected.textureDone ? 'var(--gf-success)' : 'var(--gf-text-3)'} />
      </Section>

      <Section label="Transform">
        <Vec3Row label="Position" values={[0, 0, 0]} />
        <Vec3Row label="Rotation" values={[0, 0, 0]} />
        <Vec3Row label="Scale"    values={[1, 1, 1]} />
      </Section>
    </div>
  )
}

// ─── UV Tab ────────────────────────────────────────────────────────────────────
function UVTab({ selected }) {
  const [atlasSize, setAtlasSize]   = useState(1024)
  const [padding, setPadding]       = useState(2)
  const [running, setRunning]       = useState(false)
  const [progress, setProgress]     = useState(null)
  const [uvPreview, setUvPreview]   = useState(null)
  const { updateObject, setActiveJob, clearActiveJob } = useSceneStore()

  if (!selected) return <Empty msg="Select an object to unwrap UVs" />

  const handleUnwrap = async () => {
    if (!selected.file) return
    setRunning(true)
    setProgress({ stage: 'Starting…', progress: 0 })

    try {
      const job = await createUVTextureJob({
        meshFile: selected.file,
        prompt: 'placeholder',
        textureSize: atlasSize,
        outputFormat: 'glb',
      })

      setActiveJob({ id: job.job_id, type: 'UV Unwrap', status: 'running', progress: 0, stage: 'Starting' })

      pollJob(
        job.job_id,
        (j) => {
          setProgress(j)
          setActiveJob({ id: j.id, type: 'UV Unwrap', ...j })
        },
        (j) => {
          setRunning(false)
          setProgress(j)
          clearActiveJob()
          setUvPreview(getPreviewUrl(j.id, 'uv_layout'))
          updateObject(selected.id, { uvDone: true, jobId: j.id })
        },
        (err) => {
          setRunning(false)
          setProgress({ stage: `Error: ${err.message}`, progress: 0 })
          clearActiveJob()
        }
      )
    } catch (e) {
      setRunning(false)
      setProgress({ stage: `Error: ${e.message}`, progress: 0 })
    }
  }

  return (
    <div style={{ padding: 10 }}>
      <Section label="UV Unwrap Settings">
        <FieldRow label="Atlas Size">
          <select value={atlasSize} onChange={e => setAtlasSize(+e.target.value)} style={selectStyle}>
            <option value={512}>512 × 512</option>
            <option value={1024}>1024 × 1024</option>
            <option value={2048}>2048 × 2048</option>
          </select>
        </FieldRow>
        <FieldRow label="Island Padding">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="range" min={1} max={8} value={padding}
                   onChange={e => setPadding(+e.target.value)} style={{ flex: 1 }}/>
            <span style={{ fontSize: 11, color: 'var(--gf-text-2)', width: 16 }}>{padding}</span>
          </div>
        </FieldRow>
      </Section>

      <ActionBtn onClick={handleUnwrap} disabled={running || !selected.file}
                 loading={running} label="Auto Unwrap UVs" />

      {progress && (
        <div style={{ marginTop: 8 }}>
          <ProgressBar stage={progress.stage} pct={progress.progress} />
        </div>
      )}

      {uvPreview && (
        <div style={{ marginTop: 12 }}>
          <Section label="UV Layout">
            <img src={uvPreview} style={{ width: '100%', borderRadius: 4, border: '1px solid var(--gf-border)' }} />
          </Section>
        </div>
      )}
    </div>
  )
}

// ─── Texture Tab ───────────────────────────────────────────────────────────────
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
    setProgress({ stage: 'Starting…', progress: 0 })

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

      setActiveJob({ id: job.job_id, type: 'Texture Gen', status: 'running', progress: 0, stage: 'Starting' })

      pollJob(
        job.job_id,
        (j) => { setProgress(j); setActiveJob({ id: j.id, type: 'Texture Gen', ...j }) },
        (j) => {
          setRunning(false)
          setProgress(j)
          clearActiveJob()
          setTexPreview(getPreviewUrl(j.id, 'texture'))
          updateObject(selected.id, { textureDone: true, texturePrompt: prompt, jobId: j.id })
        },
        (err) => { setRunning(false); setProgress({ stage: `Error: ${err.message}`, progress: 0 }); clearActiveJob() }
      )
    } catch (e) {
      setRunning(false)
      setProgress({ stage: `Error: ${e.message}`, progress: 0 })
    }
  }

  const quickPrompts = ['Rusted Iron', 'Marble', 'Wood', 'Concrete', 'Leather', 'Gold']

  return (
    <div style={{ padding: 10 }}>
      <Section label="Texture Prompt">
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)}
          style={{
            width: '100%', background: 'var(--gf-bg-3)',
            border: '1px solid var(--gf-border)', borderRadius: 4,
            color: 'var(--gf-text)', fontSize: 12, padding: 8,
            resize: 'vertical', minHeight: 56, fontFamily: 'inherit',
          }}
        />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
          {quickPrompts.map(q => (
            <button key={q} onClick={() => setPrompt(q.toLowerCase() + ', detailed PBR material')}
              style={{
                padding: '2px 8px', fontSize: 10,
                background: 'var(--gf-bg-3)', border: '1px solid var(--gf-border)',
                borderRadius: 12, color: 'var(--gf-text-3)', cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gf-forge)'; e.currentTarget.style.color = 'var(--gf-forge)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--gf-border)'; e.currentTarget.style.color = 'var(--gf-text-3)' }}
            >{q}</button>
          ))}
        </div>
      </Section>

      <Section label="Reference Image (optional)">
        <div onClick={() => refInput.current?.click()} style={{
          border: `1px dashed ${refFile ? 'var(--gf-forge)' : 'var(--gf-border)'}`,
          borderRadius: 4, padding: '8px 12px', textAlign: 'center',
          cursor: 'pointer', fontSize: 11, color: 'var(--gf-text-3)',
          background: 'var(--gf-bg-2)',
        }}>
          {refFile ? refFile.name : 'Click to select reference image'}
        </div>
        <input ref={refInput} type="file" accept="image/*" hidden
               onChange={e => setRefFile(e.target.files[0] || null)} />
      </Section>

      <Section label="Settings">
        <FieldRow label="Texture Size">
          <select value={texSize} onChange={e => setTexSize(+e.target.value)} style={selectStyle}>
            <option value={512}>512</option>
            <option value={1024}>1024</option>
            <option value={2048}>2048</option>
          </select>
        </FieldRow>
        <FieldRow label="AI Mode">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <ToggleSwitch checked={useAI} onChange={setUseAI} />
            <span style={{ fontSize: 10, color: 'var(--gf-text-3)' }}>
              {useAI ? 'Stable Diffusion' : 'Procedural (fast)'}
            </span>
          </div>
        </FieldRow>
        {useAI && (
          <FieldRow label={`Steps: ${aiSteps}`}>
            <input type="range" min={10} max={50} value={aiSteps}
                   onChange={e => setAiSteps(+e.target.value)} style={{ width: '100%' }}/>
          </FieldRow>
        )}
      </Section>

      <ActionBtn onClick={handleGenerate} disabled={running || !selected.file}
                 loading={running} label="Generate Texture" />

      {progress && <div style={{ marginTop: 8 }}><ProgressBar stage={progress.stage} pct={progress.progress} /></div>}

      {texPreview && (
        <div style={{ marginTop: 12 }}>
          <Section label="Generated Texture">
            <img src={texPreview} style={{ width: '100%', borderRadius: 4, border: '1px solid var(--gf-border)' }} />
          </Section>
        </div>
      )}
    </div>
  )
}

// ─── Shared sub-components ────────────────────────────────────────────────────
function Section({ label, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                    letterSpacing: '0.8px', color: 'var(--gf-text-3)',
                    padding: '4px 0 6px', borderBottom: '1px solid var(--gf-border)',
                    marginBottom: 8 }}>
        {label}
      </div>
      {children}
    </div>
  )
}

function PropRow({ label, value, valueColor }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', fontSize: 12 }}>
      <span style={{ color: 'var(--gf-text-3)' }}>{label}</span>
      <span style={{ color: valueColor || 'var(--gf-text-2)' }}>{value}</span>
    </div>
  )
}

function Vec3Row({ label, values }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <span style={{ fontSize: 10, color: 'var(--gf-text-3)', display: 'block', marginBottom: 3 }}>{label}</span>
      <div style={{ display: 'flex', gap: 4 }}>
        {['X','Y','Z'].map((axis, i) => (
          <div key={axis} style={{ flex: 1, display: 'flex', alignItems: 'center',
                                    background: 'var(--gf-bg-3)', borderRadius: 3,
                                    border: '1px solid var(--gf-border)', overflow: 'hidden' }}>
            <span style={{ padding: '0 4px', fontSize: 10, color: ['#ef4444','#22c55e','#6366f1'][i],
                           fontWeight: 700, borderRight: '1px solid var(--gf-border)' }}>{axis}</span>
            <input type="number" defaultValue={values[i]} style={{
              width: '100%', background: 'transparent', border: 'none',
              color: 'var(--gf-text-2)', fontSize: 11, padding: '3px 4px',
              textAlign: 'right',
            }}/>
          </div>
        ))}
      </div>
    </div>
  )
}

function FieldRow({ label, children }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <span style={{ fontSize: 11, color: 'var(--gf-text-3)', display: 'block', marginBottom: 4 }}>{label}</span>
      {children}
    </div>
  )
}

function ActionBtn({ onClick, disabled, loading, label }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      width: '100%', height: 32,
      background: disabled ? 'var(--gf-bg-3)' : 'var(--gf-forge)',
      border: `1px solid ${disabled ? 'var(--gf-border)' : 'var(--gf-forge)'}`,
      borderRadius: 'var(--gf-radius-sm)',
      color: disabled ? 'var(--gf-text-3)' : '#fff',
      fontSize: 12, fontWeight: 600,
      cursor: disabled ? 'not-allowed' : 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
      transition: 'all 0.15s',
    }}>
      {loading && <div className="animate-spin" style={{
        width: 12, height: 12, border: '2px solid rgba(255,255,255,0.3)',
        borderTopColor: '#fff', borderRadius: '50%',
      }}/>}
      {label}
    </button>
  )
}

function ProgressBar({ stage, pct }) {
  return (
    <div style={{ background: 'var(--gf-bg-2)', border: '1px solid var(--gf-border)',
                  borderRadius: 4, padding: '8px 10px' }}>
      <div style={{ fontSize: 11, color: 'var(--gf-text-2)', marginBottom: 6 }}>{stage}</div>
      <div style={{ height: 3, background: 'var(--gf-bg-3)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${pct || 0}%`,
          background: 'linear-gradient(90deg, var(--gf-forge), #ff9a5c)',
          transition: 'width 0.4s ease',
        }}/>
      </div>
    </div>
  )
}

function ToggleSwitch({ checked, onChange }) {
  return (
    <div onClick={() => onChange(!checked)} style={{
      width: 36, height: 20,
      background: checked ? 'var(--gf-forge)' : 'var(--gf-bg-3)',
      border: `1px solid ${checked ? 'var(--gf-forge)' : 'var(--gf-border)'}`,
      borderRadius: 10, cursor: 'pointer', position: 'relative',
      transition: 'all 0.2s', flexShrink: 0,
    }}>
      <div style={{
        position: 'absolute', top: 2,
        left: checked ? 17 : 2,
        width: 14, height: 14, borderRadius: '50%',
        background: checked ? '#fff' : 'var(--gf-text-3)',
        transition: 'left 0.2s',
      }}/>
    </div>
  )
}

function Empty({ msg }) {
  return (
    <div style={{ padding: 20, textAlign: 'center', color: 'var(--gf-text-3)', fontSize: 12 }}>
      {msg}
    </div>
  )
}

const selectStyle = {
  width: '100%', background: 'var(--gf-bg-3)',
  border: '1px solid var(--gf-border)', borderRadius: 4,
  color: 'var(--gf-text)', fontSize: 12, padding: '4px 6px',
}
