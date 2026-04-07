import React, { useRef } from 'react'
import { useUIStore, useSceneStore } from '../store'

export default function LeftPanel() {
  const { activeLeftTab, setLeftTab } = useUIStore()
  const { objects, selectedIds, selectObject, removeObject } = useSceneStore()

  return (
    <div style={{
      width: 'var(--left-panel-w)',
      background: 'var(--gf-bg-1)',
      borderRight: '1px solid var(--gf-border)',
      display: 'flex', flexDirection: 'column',
      flexShrink: 0, overflow: 'hidden',
    }}>
      {/* Tab bar */}
      <div className="flex" style={{ borderBottom: '1px solid var(--gf-border)', flexShrink: 0 }}>
        {['scene', 'tools', 'generate'].map(tab => (
          <button key={tab} onClick={() => setLeftTab(tab)} style={{
            flex: 1, height: 34,
            background: activeLeftTab === tab ? 'var(--gf-bg-2)' : 'transparent',
            border: 'none',
            borderBottom: activeLeftTab === tab ? '2px solid var(--gf-forge)' : '2px solid transparent',
            color: activeLeftTab === tab ? 'var(--gf-text)' : 'var(--gf-text-3)',
            fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px',
            cursor: 'pointer', transition: 'all 0.15s',
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
      </div>
    </div>
  )
}

// ─── Scene Hierarchy ─────────────────────────────────────────────────────────
function SceneTab({ objects, selectedIds, selectObject, removeObject }) {
  const fileInputRef = useRef()
  const { addObject } = useSceneStore()

  const handleImport = (e) => {
    const file = e.target.files[0]
    if (!file) return
    const id = `obj_${Date.now()}`
    addObject({
      id, name: file.name.replace(/\.[^.]+$/, ''),
      type: 'mesh', file,
      visible: true, selected: false,
      uvDone: false, textureDone: false,
    })
    e.target.value = ''
  }

  return (
    <div style={{ padding: '8px 0' }}>
      {/* Import button */}
      <div style={{ padding: '0 8px 8px' }}>
        <button
          onClick={() => fileInputRef.current?.click()}
          style={{
            width: '100%', height: 30,
            background: 'var(--gf-bg-3)',
            border: '1px solid var(--gf-border)',
            borderRadius: 'var(--gf-radius-sm)',
            color: 'var(--gf-text-2)', fontSize: 12,
            cursor: 'pointer', display: 'flex',
            alignItems: 'center', justifyContent: 'center', gap: 6,
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gf-forge)'; e.currentTarget.style.color = 'var(--gf-forge)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--gf-border)'; e.currentTarget.style.color = 'var(--gf-text-2)' }}
        >
          <span>+</span> Import Model
        </button>
        <input ref={fileInputRef} type="file"
               accept=".obj,.glb,.gltf,.stl,.ply,.dae"
               hidden onChange={handleImport} />
      </div>

      {/* Section header */}
      <SectionHeader label="Scene Objects" count={objects.length} />

      {/* Object list */}
      {objects.length === 0 ? (
        <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--gf-text-3)', fontSize: 11 }}>
          No objects in scene.<br/>Import a model to begin.
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
  return (
    <div
      onClick={onSelect}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '5px 8px 5px 12px',
        background: selected ? 'rgba(255,107,43,0.1)' : 'transparent',
        borderLeft: selected ? '2px solid var(--gf-forge)' : '2px solid transparent',
        cursor: 'pointer', transition: 'all 0.1s',
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = 'var(--gf-bg-2)' }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = 'transparent' }}
    >
      {/* Mesh icon */}
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="var(--gf-text-3)" strokeWidth="1.2">
        <path d="M6 1 L11 4 L11 8 L6 11 L1 8 L1 4 Z"/>
      </svg>

      {/* Name */}
      <span style={{ flex: 1, fontSize: 12, color: selected ? 'var(--gf-text)' : 'var(--gf-text-2)',
                     overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {obj.name}
      </span>

      {/* Status badges */}
      <div className="flex items-center gap-1">
        {obj.uvDone      && <StatusDot color="var(--gf-info)"    title="UV unwrapped" />}
        {obj.textureDone && <StatusDot color="var(--gf-success)" title="Textured" />}
      </div>

      {/* Remove */}
      <button
        onClick={e => { e.stopPropagation(); onRemove() }}
        style={{ background: 'none', border: 'none', color: 'var(--gf-text-3)',
                 cursor: 'pointer', fontSize: 14, padding: '0 2px',
                 opacity: 0, transition: 'opacity 0.15s' }}
        onMouseEnter={e => { e.currentTarget.style.opacity = 1; e.currentTarget.style.color = 'var(--gf-danger)' }}
        onMouseLeave={e => { e.currentTarget.style.opacity = 0 }}
      >×</button>
    </div>
  )
}

function StatusDot({ color, title }) {
  return <span title={title} style={{
    width: 6, height: 6, borderRadius: '50%',
    background: color, flexShrink: 0,
  }}/>
}

// ─── Tools Tab ───────────────────────────────────────────────────────────────
function ToolsTab() {
  const toolGroups = [
    { label: 'UV Tools', tools: [
      { name: 'Auto Unwrap', desc: 'xatlas ABF++ algorithm', icon: '⊞' },
      { name: 'UV Checker',  desc: 'Apply checkerboard',     icon: '⊟' },
    ]},
    { label: 'Texture Tools', tools: [
      { name: 'Generate Texture', desc: 'Procedural or AI',  icon: '◈' },
      { name: 'Bake Texture',     desc: 'Bake to UV space',  icon: '◉' },
    ]},
    { label: 'Mesh Tools', tools: [
      { name: 'Clean Mesh',    desc: 'Fix normals, remove duplicates', icon: '◎' },
      { name: 'Remesh',        desc: 'Uniform quad remesh',           icon: '⊠' },
    ]},
  ]

  return (
    <div style={{ padding: 8 }}>
      {toolGroups.map(g => (
        <div key={g.label} style={{ marginBottom: 12 }}>
          <SectionHeader label={g.label} />
          {g.tools.map(t => (
            <ToolRow key={t.name} {...t} />
          ))}
        </div>
      ))}
    </div>
  )
}

function ToolRow({ name, desc, icon }) {
  return (
    <button style={{
      width: '100%', padding: '7px 10px',
      background: 'var(--gf-bg-2)', border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius-sm)',
      display: 'flex', alignItems: 'center', gap: 8,
      cursor: 'pointer', marginBottom: 4,
      transition: 'all 0.15s', textAlign: 'left',
    }}
    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gf-forge)'; e.currentTarget.style.background = 'var(--gf-bg-3)' }}
    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--gf-border)'; e.currentTarget.style.background = 'var(--gf-bg-2)' }}
    >
      <span style={{ fontSize: 16, color: 'var(--gf-forge)' }}>{icon}</span>
      <div>
        <div style={{ fontSize: 12, color: 'var(--gf-text)', fontWeight: 500 }}>{name}</div>
        <div style={{ fontSize: 10, color: 'var(--gf-text-3)' }}>{desc}</div>
      </div>
    </button>
  )
}

// ─── Generate Tab (Image-to-3D from Modly) ───────────────────────────────────
function GenerateTab() {
  const [imageFile, setImageFile] = React.useState(null)
  const [preview, setPreview]     = React.useState(null)
  const fileRef = useRef()

  const handleFile = (f) => {
    setImageFile(f)
    setPreview(URL.createObjectURL(f))
  }

  return (
    <div style={{ padding: 8 }}>
      <SectionHeader label="Image → 3D Model" />
      <p style={{ fontSize: 11, color: 'var(--gf-text-3)', padding: '0 2px 8px', lineHeight: 1.6 }}>
        Generate a 3D mesh from any photo using local AI models (Hunyuan3D, TripoSG, TRELLIS).
      </p>

      {/* Image drop area */}
      <div
        onClick={() => fileRef.current?.click()}
        style={{
          border: `2px dashed ${imageFile ? 'var(--gf-forge)' : 'var(--gf-border)'}`,
          borderRadius: 'var(--gf-radius)',
          padding: 16, textAlign: 'center',
          cursor: 'pointer', background: 'var(--gf-bg-2)',
          transition: 'all 0.15s', marginBottom: 8,
        }}
      >
        {preview
          ? <img src={preview} style={{ width: '100%', borderRadius: 4, maxHeight: 120, objectFit: 'cover' }} />
          : <>
              <div style={{ fontSize: 24, marginBottom: 4 }}>🖼</div>
              <div style={{ fontSize: 11, color: 'var(--gf-text-3)' }}>Click to select reference image</div>
            </>
        }
      </div>
      <input ref={fileRef} type="file" accept="image/*" hidden
             onChange={e => e.target.files[0] && handleFile(e.target.files[0])} />

      <button style={{
        width: '100%', height: 32,
        background: imageFile ? 'var(--gf-forge)' : 'var(--gf-bg-3)',
        border: `1px solid ${imageFile ? 'var(--gf-forge)' : 'var(--gf-border)'}`,
        borderRadius: 'var(--gf-radius-sm)',
        color: imageFile ? '#fff' : 'var(--gf-text-3)',
        fontSize: 12, fontWeight: 600, cursor: imageFile ? 'pointer' : 'not-allowed',
        transition: 'all 0.15s',
      }}>
        Generate 3D Model
      </button>

      <div style={{ marginTop: 12 }}>
        <SectionHeader label="AI Models" />
        {['Hunyuan3D Mini', 'TripoSG', 'TRELLIS.2'].map(m => (
          <div key={m} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '5px 8px', background: 'var(--gf-bg-2)',
            border: '1px solid var(--gf-border)', borderRadius: 'var(--gf-radius-sm)',
            marginBottom: 4, fontSize: 11,
          }}>
            <span style={{ color: 'var(--gf-text-2)' }}>{m}</span>
            <span style={{
              color: 'var(--gf-text-3)', background: 'var(--gf-bg-3)',
              padding: '1px 6px', borderRadius: 3, fontSize: 10,
            }}>Not installed</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SectionHeader({ label, count }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '4px 10px 4px',
      fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.8px', color: 'var(--gf-text-3)',
    }}>
      <span>{label}</span>
      {count !== undefined && <span style={{ background: 'var(--gf-bg-3)', padding: '0 5px', borderRadius: 3 }}>{count}</span>}
    </div>
  )
}
