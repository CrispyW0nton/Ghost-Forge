import React, { useRef, useState, useEffect } from 'react'
import { useUIStore, useSceneStore } from '../store'
import { useModelsStore, useSlicesStore, useWorkersStore } from '../store/v2'
import { Workers } from '../modules/apiV2'
import MatrixRain from './MatrixRain'
import { getMeshInfo, pollJob } from '../modules/api'

export default function LeftPanel() {
  const { activeLeftTab, setLeftTab } = useUIStore()
  const { objects, selectedIds, selectObject, removeObject } = useSceneStore()

  const tabs = ['SCENE', 'TOOLS', 'GEN_3D', 'FORGE']

  return (
    <div style={{
      width: 'var(--left-panel-w)',
      background: 'var(--gf-bg-1)',
      borderRight: '1px solid var(--gf-border)',
      boxShadow: '1px 0 0 #39FF1410',
      display: 'flex', flexDirection: 'column',
      flexShrink: 0, overflow: 'hidden',
      position: 'relative',
    }}>
      {/* Faint matrix rain in the background */}
      <MatrixRain opacity={0.025} fontSize={11} speed={0.4} />

      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Tab bar */}
        <div style={{
          display: 'flex',
          borderBottom: '1px solid var(--gf-border)',
          flexShrink: 0,
        }}>
          {tabs.map(tab => (
            <button key={tab} onClick={() => setLeftTab(tabKey(tab))} style={{
              flex: 1, height: 32,
              background: activeLeftTab === tabKey(tab) ? 'var(--gf-bg-3)' : 'transparent',
              border: 'none',
              borderBottom: activeLeftTab === tabKey(tab)
                ? '2px solid var(--gf-neon)'
                : '2px solid transparent',
              color: activeLeftTab === tabKey(tab) ? 'var(--gf-neon)' : 'var(--gf-text-3)',
              fontSize: 9, fontWeight: 700,
              letterSpacing: '0.1em', textTransform: 'uppercase',
              fontFamily: 'monospace', cursor: 'pointer',
              transition: 'all 0.12s',
              textShadow: activeLeftTab === tabKey(tab) ? '0 0 6px var(--gf-neon)' : 'none',
            }}>
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {activeLeftTab === 'scene'    && <SceneTab objects={objects} selectedIds={selectedIds} selectObject={selectObject} removeObject={removeObject} />}
          {activeLeftTab === 'tools'    && <ToolsTab />}
          {activeLeftTab === 'generate' && <GenerateTab />}
          {activeLeftTab === 'forge'    && <ForgeTab />}
        </div>
      </div>
    </div>
  )
}

function tabKey(t) {
  // Map display labels to internal keys.
  return t.toLowerCase().replace('gen_3d', 'generate')
}

// ─── Scene Hierarchy ──────────────────────────────────────────────────────────
function SceneTab({ objects, selectedIds, selectObject, removeObject }) {
  const fileInputRef = useRef()
  const { addObject } = useSceneStore()

  const handleImport = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const id = `obj_${Date.now()}`
    // Add object immediately with a loading flag for mesh stats
    addObject({
      id,
      name: file.name.replace(/\.[^.]+$/, ''),
      type: 'mesh',
      file,
      visible: true,
      selected: false,
      uvDone: false,
      textureDone: false,
      meshStats: { loading: true },
    })
    // Auto-select the newly imported object
    useSceneStore.getState().selectObject(id)
    e.target.value = ''

    // Fetch mesh stats from backend (non-blocking)
    try {
      const info = await getMeshInfo(file)
      useSceneStore.getState().updateObject(id, { meshStats: info })
    } catch (_) {
      // Stats unavailable — clear the loading flag silently
      useSceneStore.getState().updateObject(id, { meshStats: {} })
    }
  }

  return (
    <div style={{ padding: '6px 0' }}>
      {/* Import button */}
      <div style={{ padding: '0 8px 6px' }}>
        <button onClick={() => fileInputRef.current?.click()} style={{
          width: '100%', height: 28,
          background: 'transparent',
          border: '1px solid var(--gf-border-h)',
          borderRadius: 'var(--gf-radius-sm)',
          color: 'var(--gf-text-3)', fontSize: 9,
          fontFamily: 'monospace', letterSpacing: '0.1em',
          textTransform: 'uppercase',
          cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
          transition: 'all 0.12s',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = 'var(--gf-neon)'
          e.currentTarget.style.color = 'var(--gf-neon)'
          e.currentTarget.style.boxShadow = '0 0 8px #39FF1420'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = 'var(--gf-border-h)'
          e.currentTarget.style.color = 'var(--gf-text-3)'
          e.currentTarget.style.boxShadow = 'none'
        }}>
          <span style={{ color: 'var(--gf-neon)', fontWeight: 700 }}>+</span>
          IMPORT_MODEL
        </button>
        <input ref={fileInputRef} type="file" accept=".obj,.glb,.gltf,.stl,.ply,.dae" hidden onChange={handleImport} />
      </div>

      <SectionHeader label="SCENE_OBJECTS" count={objects.length} />

      {objects.length === 0 ? (
        <div style={{ padding: '20px 10px', textAlign: 'center', color: 'var(--gf-text-4)', fontSize: 9, fontFamily: 'monospace', letterSpacing: '0.08em', lineHeight: 2 }}>
          <div style={{ color: 'var(--gf-neon-dim)', marginBottom: 4 }}>// EMPTY SCENE</div>
          <div>IMPORT A MODEL TO BEGIN</div>
        </div>
      ) : (
        objects.map(obj => (
          <ObjectRow key={obj.id} obj={obj}
            selected={selectedIds.includes(obj.id)}
            onSelect={() => selectObject(obj.id)}
            onRemove={() => removeObject(obj.id)} />
        ))
      )}
    </div>
  )
}

function ObjectRow({ obj, selected, onSelect, onRemove }) {
  const [hover, setHover] = React.useState(false)
  return (
    <div
      onClick={onSelect}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '5px 8px 5px 10px',
        background: selected ? 'rgba(57,255,20,0.07)' : hover ? 'var(--gf-bg-3)' : 'transparent',
        borderLeft: `2px solid ${selected ? 'var(--gf-neon)' : 'transparent'}`,
        boxShadow: selected ? 'inset 0 0 10px #39FF1408' : 'none',
        cursor: 'pointer', transition: 'all 0.1s',
      }}
    >
      {/* Mesh icon */}
      <svg width="11" height="11" viewBox="0 0 12 12" fill="none"
           stroke={selected ? 'var(--gf-neon)' : 'var(--gf-text-3)'} strokeWidth="1">
        <path d="M6 1 L11 3.5 L11 8.5 L6 11 L1 8.5 L1 3.5 Z"/>
        <path d="M1 3.5L6 6L11 3.5M6 6V11" strokeDasharray="1.5 1"/>
      </svg>

      <span style={{
        flex: 1, fontSize: 10, fontFamily: 'monospace',
        color: selected ? 'var(--gf-neon)' : 'var(--gf-text-2)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        textShadow: selected ? '0 0 6px var(--gf-neon)' : 'none',
      }}>
        {obj.name}
      </span>

      <div style={{ display: 'flex', gap: 3 }}>
        {obj.uvDone      && <NeonDot color="var(--gf-cyan)"  title="UV Unwrapped" />}
        {obj.textureDone && <NeonDot color="var(--gf-neon)"  title="Textured" />}
      </div>

      {hover && (
        <button onClick={e => { e.stopPropagation(); onRemove() }} style={{
          background: 'none', border: 'none', color: 'var(--gf-danger)',
          cursor: 'pointer', fontSize: 13, padding: '0 2px',
          lineHeight: 1, fontFamily: 'monospace',
        }}>×</button>
      )}
    </div>
  )
}

function NeonDot({ color, title }) {
  return (
    <span title={title} style={{
      width: 5, height: 5, borderRadius: '50%',
      background: color, flexShrink: 0,
      boxShadow: `0 0 4px ${color}`,
    }}/>
  )
}

// ─── Tools Tab ────────────────────────────────────────────────────────────────
function ToolsTab() {
  const groups = [
    { label: 'UV_TOOLS', tools: [
      { name: 'AUTO_UNWRAP', desc: 'xatlas ABF++ algorithm', icon: '⊞', color: 'var(--gf-neon)' },
      { name: 'UV_CHECKER', desc: 'Apply checkerboard map', icon: '⊟', color: 'var(--gf-cyan)' },
    ]},
    { label: 'TEXTURE_TOOLS', tools: [
      { name: 'GEN_TEXTURE',  desc: 'Procedural or SD AI',   icon: '◈', color: 'var(--gf-neon)' },
      { name: 'BAKE_TEXTURE', desc: 'Bake to UV atlas',       icon: '◉', color: 'var(--gf-cyan)' },
    ]},
    { label: 'MESH_TOOLS', tools: [
      { name: 'CLEAN_MESH', desc: 'Fix normals / remove dupes', icon: '◎', color: 'var(--gf-neon)' },
      { name: 'REMESH',     desc: 'Uniform quad remesh',        icon: '⊠', color: 'var(--gf-cyan)' },
    ]},
  ]

  return (
    <div style={{ padding: 8 }}>
      {groups.map(g => (
        <div key={g.label} style={{ marginBottom: 10 }}>
          <SectionHeader label={g.label} />
          {g.tools.map(t => <ToolBtn key={t.name} {...t} />)}
        </div>
      ))}
    </div>
  )
}

function ToolBtn({ name, desc, icon, color }) {
  const [hover, setHover] = React.useState(false)
  return (
    <button
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: '100%', padding: '6px 8px',
        background: hover ? 'var(--gf-bg-4)' : 'var(--gf-bg-2)',
        border: `1px solid ${hover ? color : 'var(--gf-border)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        display: 'flex', alignItems: 'center', gap: 8,
        cursor: 'pointer', marginBottom: 4,
        textAlign: 'left', transition: 'all 0.12s',
        boxShadow: hover ? `0 0 8px ${color}22` : 'none',
      }}
    >
      <span style={{ fontSize: 14, color, flexShrink: 0,
                     textShadow: hover ? `0 0 6px ${color}` : 'none' }}>{icon}</span>
      <div>
        <div style={{ fontSize: 9, color: hover ? color : 'var(--gf-text-2)',
                      fontFamily: 'monospace', letterSpacing: '0.08em',
                      textShadow: hover ? `0 0 5px ${color}` : 'none' }}>{name}</div>
        <div style={{ fontSize: 9, color: 'var(--gf-text-4)', marginTop: 1 }}>{desc}</div>
      </div>
    </button>
  )
}

// ─── Generate Tab (real worker registry, P10) ────────────────────────────────
//
// Replaces the old hardcoded mock list with the live worker registry from
// /api/v2/workers. Mesh generation is image/reference driven; prompts guide
// texturing and style, not text-only mesh topology.
function GenerateTab() {
  const { entries: workers, refresh, loading } = useWorkersStore()
  const { entries: models, refresh: refreshModels, download, downloading } = useModelsStore()
  const [capability, setCapability] = useState('image_to_3d')
  const [imageFile, setImageFile]   = useState(null)
  const [preview, setPreview]       = useState(null)
  const [prompt, setPrompt]         = useState('a small wooden crate, painted iron bands')
  const [selectedWorker, setWorker] = useState(null)
  const [running, setRunning]       = useState(false)
  const [status, setStatus]         = useState(null)
  const [error, setError]           = useState(null)
  const fileRef = useRef()
  const { addObject } = useSceneStore()

  useEffect(() => { refresh(); refreshModels() }, [refresh, refreshModels])

  // Auto-select the highest-priority runnable worker for the capability,
  // falling back to the first stub when none of the real workers report
  // runnable. Visual feedback below makes the choice explicit.
  useEffect(() => {
    const candidates = workers.filter(w =>
      (w.descriptor?.capabilities || []).includes(capability)
    )
    if (!candidates.length) { setWorker(null); return }
    const ordered = [...candidates].sort((a, b) => {
      const ra = a.probe?.runnable, rb = b.probe?.runnable
      if (ra !== rb) return ra ? -1 : 1
      return (b.descriptor?.priority || 0) - (a.descriptor?.priority || 0)
    })
    setWorker(ordered[0].descriptor.name)
  }, [workers, capability])

  const candidates = workers.filter(w =>
    (w.descriptor?.capabilities || []).includes(capability)
  )

  // Required model status for the chosen worker — surfaces a one-click
  // download button when weights aren't cached.
  const chosen = workers.find(w => w.descriptor?.name === selectedWorker) || null
  const requiredModels = chosen?.descriptor?.required_models || []
  const requiredStatus = requiredModels.map(id =>
    models.find(m => m.artifact?.model_id === id) || null
  ).filter(Boolean)

  const handleRun = async () => {
    setError(null)
    setStatus('SUBMITTING…')
    setRunning(true)
    try {
      const spec = buildSpec(capability, { prompt, imageFile })
      if (!spec) {
        setError('MISSING_INPUT')
        setRunning(false); setStatus(null); return
      }
      const res = await Workers.run({ capability, spec })
      setStatus('JOB_QUEUED…')
      pollJob(
        res.job_id,
        (j) => setStatus(`${j.stage?.toUpperCase() || 'PROCESSING'} ${j.progress || 0}%`),
        (j) => {
          setRunning(false); setStatus('MESH_READY')
          const id = `gen_${Date.now()}`
          addObject({
            id,
            name: `gen_${capability}_${id.slice(-4)}`,
            type: 'mesh', file: null, visible: true,
            selected: false, uvDone: false, textureDone: false,
            previewUrl: `/api/jobs/${j.id}/preview/mesh_glb`,
          })
          useSceneStore.getState().selectObject(id)
        },
        (err) => {
          setRunning(false); setError(`ERR: ${err.message}`); setStatus(null)
        }
      )
    } catch (e) {
      setRunning(false); setError(`ERR: ${e.message}`); setStatus(null)
    }
  }

  const handleDownload = async (modelId) => {
    setError(null)
    try { await download(modelId) }
    catch (e) { setError(`DOWNLOAD_FAILED: ${e.message}`) }
  }

  return (
    <div style={{ padding: 8 }}>
      <SectionHeader label="GENERATE" />
      <p style={{ fontSize: 9, color: 'var(--gf-text-3)', padding: '0 2px 6px',
                  lineHeight: 1.8, fontFamily: 'monospace', letterSpacing: '0.05em' }}>
        // Image-to-3D + AI texturing worker registry<br/>
        // Mesh generation requires a reference image
      </p>

      {/* Capability selector */}
      <CapabilityRow capability={capability} onChange={setCapability} disabled={running} />

      {/* Per-capability inputs */}
      {(capability === 'image_to_3d' || capability === 'texture_mesh') && (
        <ImageInput
          file={imageFile} preview={preview}
          onPick={(f) => { setImageFile(f); setPreview(URL.createObjectURL(f)) }}
          fileRef={fileRef}
          label={capability === 'image_to_3d' ? 'REFERENCE_IMAGE' : 'CONCEPT_IMAGE (optional)'}
        />
      )}
      {capability === 'texture_mesh' && (
        <PromptInput value={prompt} onChange={setPrompt} disabled={running} />
      )}

      {/* Worker picker */}
      <div style={{ marginBottom: 8 }}>
        <div style={{
          fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
          letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4,
        }}>
          <span style={{ color: 'var(--gf-neon-dim)' }}>// </span>WORKER
          {loading && (
            <span style={{ color: 'var(--gf-text-4)', marginLeft: 6 }}>(probing…)</span>
          )}
        </div>
        {candidates.length === 0 ? (
          <div style={{
            padding: '10px 8px', textAlign: 'center',
            color: 'var(--gf-text-4)', fontSize: 9, fontFamily: 'monospace',
          }}>// no workers registered</div>
        ) : candidates.map(w => (
          <WorkerRow key={w.descriptor.name} entry={w}
            selected={selectedWorker === w.descriptor.name}
            onSelect={() => !running && setWorker(w.descriptor.name)} />
        ))}
      </div>

      {/* Required model downloads (if any) */}
      {requiredStatus.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{
            fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
            letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4,
          }}>
            <span style={{ color: 'var(--gf-neon-dim)' }}>// </span>WEIGHTS
          </div>
          {requiredStatus.map(({ artifact, status }) => (
            <ModelRow key={artifact.model_id} artifact={artifact} status={status}
              busy={!!downloading[artifact.model_id]}
              onDownload={() => handleDownload(artifact.model_id)} />
          ))}
        </div>
      )}

      <MatrixButton
        onClick={handleRun}
        disabled={running || !selectedWorker}
        loading={running}
        label={capability === 'image_to_3d' ? 'GENERATE_FROM_IMAGE' :
               capability === 'texture_mesh' ? 'TEXTURE_MESH' : 'REFINE_MESH'}
      />

      {/* Status / error display */}
      {status && (
        <div style={{
          marginTop: 7, padding: '5px 8px',
          background: 'rgba(57,255,20,0.04)',
          border: '1px solid rgba(57,255,20,0.2)',
          borderRadius: 'var(--gf-radius-sm)',
          fontSize: 9, color: 'var(--gf-neon)',
          fontFamily: 'monospace', letterSpacing: '0.08em',
        }}>
          &gt; {status}
        </div>
      )}
      {error && (
        <div style={{
          marginTop: 7, padding: '5px 8px',
          background: 'rgba(255,45,85,0.05)',
          border: '1px solid rgba(255,45,85,0.25)',
          borderRadius: 'var(--gf-radius-sm)',
          fontSize: 9, color: 'var(--gf-danger)',
          fontFamily: 'monospace', letterSpacing: '0.06em',
        }}>
          {error}
        </div>
      )}
    </div>
  )
}

function buildSpec(capability, { prompt, imageFile }) {
  // For now we lean on the durable runner: the spec needs an output
  // directory. The backend resolves a per-asset folder under data/assets,
  // so we just supply a placeholder the operations layer overrides.
  const base = { output_dir: `assets/_ui_${Date.now()}`, seed: null }
  if (capability === 'image_to_3d') {
    if (!imageFile) return null
    // The renderer can't directly upload binary into a JSON endpoint
    // here; for the v2 /workers/run path we expect a path. Stub workers
    // synthesise their output regardless of the path, so this works for
    // smoke testing. Real workers go through the slice executor (FORGE
    // tab) which knows how to upload files first.
    return { ...base, image_path: imageFile.name }
  }
  if (capability === 'texture_mesh') {
    return { ...base, prompt: prompt || 'worn stone',
             input_mesh_path: 'last_mesh.glb', texture_size: 512 }
  }
  if (capability === 'refine_mesh') {
    return { ...base, input_mesh_path: 'last_mesh.glb' }
  }
  return null
}

function CapabilityRow({ capability, onChange, disabled }) {
  const caps = [
    { id: 'image_to_3d',  label: 'IMG→3D' },
    { id: 'texture_mesh', label: 'TEX' },
    { id: 'refine_mesh',  label: 'REFINE' },
  ]
  return (
    <div style={{ display: 'flex', gap: 3, marginBottom: 8 }}>
      {caps.map(c => (
        <button key={c.id} onClick={() => !disabled && onChange(c.id)} style={{
          flex: 1, height: 24,
          background: capability === c.id ? 'rgba(57,255,20,0.1)' : 'var(--gf-bg-2)',
          border: `1px solid ${capability === c.id ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
          borderRadius: 'var(--gf-radius-sm)',
          color: capability === c.id ? 'var(--gf-neon)' : 'var(--gf-text-3)',
          fontSize: 9, fontFamily: 'monospace', letterSpacing: '0.08em',
          fontWeight: 700, cursor: disabled ? 'default' : 'pointer',
          textShadow: capability === c.id ? '0 0 5px var(--gf-neon)' : 'none',
        }}>{c.label}</button>
      ))}
    </div>
  )
}

function ImageInput({ file, preview, onPick, fileRef, label }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div onClick={() => fileRef.current?.click()} style={{
        border: `1px dashed ${file ? 'var(--gf-neon)' : 'var(--gf-border-h)'}`,
        borderRadius: 'var(--gf-radius)',
        padding: file ? 4 : 12,
        textAlign: 'center', cursor: 'pointer',
        background: file ? 'rgba(57,255,20,0.04)' : 'var(--gf-bg-2)',
        boxShadow: file ? '0 0 10px #39FF1418' : 'none',
        transition: 'all 0.15s',
      }}>
        {preview
          ? <img src={preview} style={{
              width: '100%', borderRadius: 3, maxHeight: 100, objectFit: 'cover',
              border: '1px solid var(--gf-neon-dim)',
            }} alt="Reference" />
          : <>
              <div style={{ fontSize: 16, marginBottom: 3 }}>◬</div>
              <div style={{
                fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
                letterSpacing: '0.08em',
              }}>{label}</div>
            </>
        }
      </div>
      <input ref={fileRef} type="file" accept="image/*" hidden
             onChange={e => e.target.files[0] && onPick(e.target.files[0])} />
    </div>
  )
}

function PromptInput({ value, onChange, disabled }) {
  return (
    <textarea
      value={value} onChange={e => onChange(e.target.value)} disabled={disabled}
      placeholder="describe the asset…"
      style={{
        width: '100%', minHeight: 50, marginBottom: 8,
        padding: '6px 8px',
        background: 'var(--gf-bg-2)',
        border: '1px solid var(--gf-border)',
        borderRadius: 'var(--gf-radius-sm)',
        color: 'var(--gf-text-2)',
        fontSize: 10, fontFamily: 'monospace',
        resize: 'vertical', outline: 'none',
      }}
    />
  )
}

function WorkerRow({ entry, selected, onSelect }) {
  const probe = entry.probe
  const desc = entry.descriptor
  const ok = probe?.runnable
  const isStub = desc?.is_stub
  const reason = probe?.reason
  return (
    <div onClick={onSelect} style={{
      padding: '5px 8px', marginBottom: 3,
      background: selected ? 'rgba(57,255,20,0.07)' : 'var(--gf-bg-2)',
      border: `1px solid ${selected ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
      borderRadius: 'var(--gf-radius-sm)',
      cursor: 'pointer', transition: 'all 0.1s',
      boxShadow: selected ? '0 0 6px #39FF1418' : 'none',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{
            fontSize: 9, fontFamily: 'monospace', letterSpacing: '0.05em',
            color: selected ? 'var(--gf-neon)' : 'var(--gf-text-2)',
            textShadow: selected ? '0 0 5px var(--gf-neon)' : 'none',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{desc.name.toUpperCase()}</div>
          {reason && !ok && (
            <div style={{
              fontSize: 8, color: 'var(--gf-text-4)', marginTop: 1,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>{reason}</div>
          )}
        </div>
        <span style={{
          fontSize: 8, fontFamily: 'monospace', padding: '1px 5px',
          borderRadius: 2, flexShrink: 0,
          background: ok ? (isStub ? 'rgba(0,255,255,0.07)' : 'rgba(57,255,20,0.1)') : 'transparent',
          border: `1px solid ${ok ? (isStub ? 'var(--gf-cyan)' : 'var(--gf-neon-dim)') : 'var(--gf-border)'}`,
          color: ok ? (isStub ? 'var(--gf-cyan)' : 'var(--gf-neon)') : 'var(--gf-text-4)',
        }}>
          {ok ? (isStub ? 'STUB' : 'READY') : 'NOT_READY'}
        </span>
      </div>
    </div>
  )
}

function ModelRow({ artifact, status, busy, onDownload }) {
  const sizeGb = artifact.total_size_bytes
    ? (artifact.total_size_bytes / 1024 / 1024 / 1024).toFixed(1) + 'GB' : ''
  return (
    <div style={{
      padding: '4px 8px', marginBottom: 3,
      background: 'var(--gf-bg-2)',
      border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius-sm)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6,
    }}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 9, fontFamily: 'monospace',
                      color: 'var(--gf-text-2)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {artifact.model_id}
        </div>
        {sizeGb && (
          <div style={{ fontSize: 8, color: 'var(--gf-text-4)', marginTop: 1 }}>{sizeGb}</div>
        )}
      </div>
      {status.cached
        ? <span style={{
            fontSize: 8, color: 'var(--gf-neon)',
            fontFamily: 'monospace', padding: '1px 5px',
            border: '1px solid var(--gf-neon-dim)', borderRadius: 2,
          }}>CACHED</span>
        : <button onClick={onDownload} disabled={busy} style={{
            fontSize: 8, padding: '2px 6px',
            background: busy ? 'var(--gf-bg-3)' : 'transparent',
            border: '1px solid var(--gf-border-h)',
            borderRadius: 2, color: 'var(--gf-text-3)',
            fontFamily: 'monospace', cursor: busy ? 'wait' : 'pointer',
          }}>
            {busy ? 'DL…' : 'DOWNLOAD'}
          </button>
      }
    </div>
  )
}

// ─── FORGE Tab — vertical slice planner + executor (P10 marquee feature) ─────
function ForgeTab() {
  const { summaries, active, refresh, open, create, execute, remove, executing, loading, error } =
    useSlicesStore()
  const [showNew, setShowNew] = useState(false)

  useEffect(() => { refresh() }, [refresh])

  return (
    <div style={{ padding: 8 }}>
      <SectionHeader label="VERTICAL_SLICES" count={summaries.length} />
      <p style={{ fontSize: 9, color: 'var(--gf-text-3)', padding: '0 2px 6px',
                  lineHeight: 1.8, fontFamily: 'monospace', letterSpacing: '0.05em' }}>
        // Plan + execute multi-asset pipelines:<br/>
        // KB → generate → unwrap → texture → audit → handoff
      </p>

      <div style={{ marginBottom: 6 }}>
        <button onClick={() => setShowNew(s => !s)} style={{
          width: '100%', height: 26,
          background: 'transparent',
          border: '1px solid var(--gf-neon-dim)',
          borderRadius: 'var(--gf-radius-sm)',
          color: 'var(--gf-neon)',
          fontSize: 9, fontFamily: 'monospace',
          letterSpacing: '0.12em', textTransform: 'uppercase',
          fontWeight: 700, cursor: 'pointer',
          textShadow: '0 0 5px var(--gf-neon)',
        }}>
          {showNew ? '— CANCEL' : '+ NEW SLICE'}
        </button>
      </div>

      {showNew && (
        <NewSliceForm
          onCancel={() => setShowNew(false)}
          onCreate={async (params) => {
            try {
              await create(params)
              setShowNew(false)
            } catch (_) { /* error already in store */ }
          }}
          loading={loading}
        />
      )}

      {summaries.length === 0 && !showNew ? (
        <div style={{ padding: '20px 10px', textAlign: 'center',
                      color: 'var(--gf-text-4)', fontSize: 9, fontFamily: 'monospace' }}>
          // NO SLICES YET<br/>// PRESS [+ NEW SLICE] TO BEGIN
        </div>
      ) : summaries.map(s => (
        <SliceRow key={s.slice_id} summary={s}
          selected={active?.plan?.slice_id === s.slice_id}
          onSelect={() => open(s.slice_id)}
          onDelete={() => remove(s.slice_id)} />
      ))}

      {active && <SliceDetail active={active} executing={executing}
        onExecute={() => execute(active.plan.slice_id)} />}

      {error && (
        <div style={{
          marginTop: 7, padding: '5px 8px',
          background: 'rgba(255,45,85,0.05)',
          border: '1px solid rgba(255,45,85,0.25)',
          borderRadius: 'var(--gf-radius-sm)',
          fontSize: 9, color: 'var(--gf-danger)',
          fontFamily: 'monospace',
        }}>{error}</div>
      )}
    </div>
  )
}

function SliceRow({ summary, selected, onSelect, onDelete }) {
  const [hover, setHover] = useState(false)
  return (
    <div
      onClick={onSelect}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        padding: '6px 8px', marginBottom: 3,
        background: selected ? 'rgba(57,255,20,0.07)' : hover ? 'var(--gf-bg-3)' : 'var(--gf-bg-2)',
        border: `1px solid ${selected ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        cursor: 'pointer', transition: 'all 0.1s',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6,
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 10, fontFamily: 'monospace',
                      color: selected ? 'var(--gf-neon)' : 'var(--gf-text-2)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      textShadow: selected ? '0 0 5px var(--gf-neon)' : 'none' }}>
          {summary.title || summary.slice_id}
        </div>
        <div style={{ fontSize: 8, color: 'var(--gf-text-4)', marginTop: 1 }}>
          {summary.asset_count || 0} ASSET(S) · {summary.target_engine?.toUpperCase()}
        </div>
      </div>
      {hover && (
        <button onClick={e => { e.stopPropagation(); onDelete() }} style={{
          background: 'none', border: 'none', color: 'var(--gf-danger)',
          cursor: 'pointer', fontSize: 13, padding: '0 2px',
        }}>×</button>
      )}
    </div>
  )
}

function SliceDetail({ active, executing, onExecute }) {
  const { plan, run } = active
  return (
    <div style={{
      marginTop: 8, padding: 6,
      border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius)',
      background: 'var(--gf-bg-2)',
    }}>
      <div style={{ fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
                    letterSpacing: '0.08em', marginBottom: 4 }}>
        <span style={{ color: 'var(--gf-neon-dim)' }}>// </span>{plan.brief?.title}
      </div>

      {plan.assets?.map(a => {
        const state = run?.asset_states?.[a.asset_id]
        return (
          <AssetStageRow key={a.asset_id} asset={a} state={state} />
        )
      })}

      <button onClick={onExecute} disabled={executing} style={{
        width: '100%', height: 26, marginTop: 6,
        background: executing ? 'var(--gf-bg-3)' : 'rgba(57,255,20,0.1)',
        border: '1px solid var(--gf-neon-dim)',
        borderRadius: 'var(--gf-radius-sm)',
        color: 'var(--gf-neon)',
        fontSize: 9, fontFamily: 'monospace', fontWeight: 700,
        letterSpacing: '0.12em', cursor: executing ? 'wait' : 'pointer',
        textShadow: '0 0 5px var(--gf-neon)',
      }}>
        {executing ? '> EXECUTING…' : '> EXECUTE_SLICE'}
      </button>
    </div>
  )
}

function AssetStageRow({ asset, state }) {
  const stages = state?.stages || []
  const overall = state?.status || 'pending'
  const color = overall === 'succeeded' ? 'var(--gf-neon)'
    : overall === 'running' ? 'var(--gf-cyan)'
    : overall === 'failed' ? 'var(--gf-danger)'
    : 'var(--gf-text-4)'
  return (
    <div style={{
      padding: '4px 6px', marginBottom: 3,
      background: 'var(--gf-bg-3)',
      border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius-sm)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 9, fontFamily: 'monospace', color: 'var(--gf-text-2)' }}>
          {asset.asset_id}
        </span>
        <span style={{ fontSize: 8, color, fontFamily: 'monospace',
                       textShadow: overall === 'succeeded' ? '0 0 5px var(--gf-neon)' : 'none' }}>
          {overall.toUpperCase()}
        </span>
      </div>
      {stages.length > 0 && (
        <div style={{ display: 'flex', gap: 2, marginTop: 3, flexWrap: 'wrap' }}>
          {stages.map((s, i) => (
            <span key={i} title={`${s.stage}: ${s.status}`} style={{
              fontSize: 7, padding: '1px 4px', borderRadius: 2,
              background: s.status === 'succeeded' ? 'rgba(57,255,20,0.1)'
                        : s.status === 'failed' ? 'rgba(255,45,85,0.1)'
                        : 'var(--gf-bg-2)',
              color: s.status === 'succeeded' ? 'var(--gf-neon)'
                   : s.status === 'failed' ? 'var(--gf-danger)'
                   : 'var(--gf-text-4)',
              fontFamily: 'monospace', letterSpacing: '0.04em',
            }}>{s.stage}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function NewSliceForm({ onCancel, onCreate, loading }) {
  const [title, setTitle] = useState('Demo Slice')
  const [engine, setEngine] = useState('unity')
  const [assetIds, setAssetIds] = useState('barrel, crate')
  const [referenceImages, setReferenceImages] = useState('concepts/barrel.png, concepts/crate.png')
  return (
    <div style={{
      padding: 6, marginBottom: 6,
      border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius)',
      background: 'var(--gf-bg-2)',
    }}>
      <FormLabel>TITLE</FormLabel>
      <FormInput value={title} onChange={setTitle} />
      <FormLabel>TARGET_ENGINE</FormLabel>
      <div style={{ display: 'flex', gap: 3, marginBottom: 5 }}>
        {['unity', 'unreal'].map(e => (
          <button key={e} onClick={() => setEngine(e)} style={{
            flex: 1, height: 22,
            background: engine === e ? 'rgba(57,255,20,0.1)' : 'var(--gf-bg-3)',
            border: `1px solid ${engine === e ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
            color: engine === e ? 'var(--gf-neon)' : 'var(--gf-text-3)',
            fontSize: 9, fontFamily: 'monospace', cursor: 'pointer',
            borderRadius: 'var(--gf-radius-sm)',
          }}>{e.toUpperCase()}</button>
        ))}
      </div>
      <FormLabel>ASSET_IDS (comma-separated)</FormLabel>
      <FormInput value={assetIds} onChange={setAssetIds} />
      <FormLabel>REFERENCE_IMAGES (comma-separated paths)</FormLabel>
      <FormInput value={referenceImages} onChange={setReferenceImages} />

      <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
        <button onClick={onCancel} style={{
          flex: 1, height: 22,
          background: 'transparent',
          border: '1px solid var(--gf-border)',
          color: 'var(--gf-text-3)',
          fontSize: 9, fontFamily: 'monospace', cursor: 'pointer',
          borderRadius: 'var(--gf-radius-sm)',
        }}>CANCEL</button>
        <button
          disabled={loading}
          onClick={() => {
            const ids = assetIds.split(',').map(s => s.trim()).filter(Boolean)
            const refs = referenceImages.split(',').map(s => s.trim()).filter(Boolean)
            onCreate({
              brief: {
                title, description: title,
                target_engine: engine, art_style: 'low-poly',
              },
              assets: ids.map((id, index) => ({
                asset_id: id, description: id,
                kind: 'prop', strategy: 'image_to_3d',
                reference_image_path: refs[index] || refs[0] || null,
                license: { spdx: 'CC0-1.0', attribution: 'auto' },
                audit_preset: 'default',
              })),
            })
          }}
          style={{
            flex: 1, height: 22,
            background: 'rgba(57,255,20,0.1)',
            border: '1px solid var(--gf-neon-dim)',
            color: 'var(--gf-neon)',
            fontSize: 9, fontFamily: 'monospace', fontWeight: 700, cursor: 'pointer',
            borderRadius: 'var(--gf-radius-sm)',
            textShadow: '0 0 5px var(--gf-neon)',
          }}>{loading ? '…' : 'CREATE'}</button>
      </div>
    </div>
  )
}

function FormLabel({ children }) {
  return <div style={{
    fontSize: 8, color: 'var(--gf-text-4)', fontFamily: 'monospace',
    letterSpacing: '0.1em', marginBottom: 2,
  }}>// {children}</div>
}

function FormInput({ value, onChange }) {
  return (
    <input value={value} onChange={e => onChange(e.target.value)}
      style={{
        width: '100%', height: 22, marginBottom: 5,
        padding: '0 6px',
        background: 'var(--gf-bg-3)',
        border: '1px solid var(--gf-border)',
        borderRadius: 'var(--gf-radius-sm)',
        color: 'var(--gf-text-2)',
        fontSize: 10, fontFamily: 'monospace',
        outline: 'none',
      }} />
  )
}

// ─── Shared components ────────────────────────────────────────────────────────
function SectionHeader({ label, count }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '3px 8px 4px',
      fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
      color: 'var(--gf-text-3)', fontFamily: 'monospace',
      borderBottom: '1px solid var(--gf-border)',
      marginBottom: 4,
    }}>
      <span><span style={{ color: 'var(--gf-neon-dim)' }}>// </span>{label}</span>
      {count !== undefined && (
        <span style={{ color: 'var(--gf-neon)', background: 'var(--gf-bg-3)',
                       padding: '0 4px', borderRadius: 2,
                       boxShadow: '0 0 4px #39FF1425' }}>{count}</span>
      )}
    </div>
  )
}

export function MatrixButton({ onClick, disabled, loading, label }) {
  const [hover, setHover] = React.useState(false)
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: '100%', height: 30,
        background: disabled ? 'transparent'
          : hover ? 'rgba(57,255,20,0.15)' : 'rgba(57,255,20,0.08)',
        border: `1px solid ${disabled ? 'var(--gf-border)' : 'var(--gf-neon-dim)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        color: disabled ? 'var(--gf-text-4)' : 'var(--gf-neon)',
        fontSize: 9, fontWeight: 700, fontFamily: 'monospace',
        letterSpacing: '0.15em', textTransform: 'uppercase',
        cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        transition: 'all 0.12s',
        boxShadow: !disabled && hover ? '0 0 12px #39FF1430' : !disabled ? '0 0 6px #39FF1418' : 'none',
        textShadow: !disabled ? '0 0 6px var(--gf-neon)' : 'none',
      }}
    >
      {loading && (
        <div className="animate-spin" style={{
          width: 10, height: 10,
          border: '1.5px solid rgba(57,255,20,0.3)',
          borderTopColor: 'var(--gf-neon)',
          borderRadius: '50%',
        }}/>
      )}
      &gt; {label}
    </button>
  )
}
