import React, { useRef } from 'react'
import { useUIStore, useSceneStore } from '../store'
import MatrixRain from './MatrixRain'

export default function LeftPanel() {
  const { activeLeftTab, setLeftTab } = useUIStore()
  const { objects, selectedIds, selectObject, removeObject } = useSceneStore()

  const tabs = ['SCENE', 'TOOLS', 'GEN_3D']

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
            <button key={tab} onClick={() => setLeftTab(tab.toLowerCase().replace('gen_3d', 'generate'))} style={{
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
        </div>
      </div>
    </div>
  )
}

function tabKey(t) {
  return t.toLowerCase().replace('gen_3d', 'generate')
}

// ─── Scene Hierarchy ──────────────────────────────────────────────────────────
function SceneTab({ objects, selectedIds, selectObject, removeObject }) {
  const fileInputRef = useRef()
  const { addObject } = useSceneStore()

  const handleImport = (e) => {
    const file = e.target.files[0]
    if (!file) return
    const id = `obj_${Date.now()}`
    addObject({ id, name: file.name.replace(/\.[^.]+$/, ''), type: 'mesh', file, visible: true, selected: false, uvDone: false, textureDone: false })
    e.target.value = ''
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

// ─── Generate Tab (Image → 3D) ────────────────────────────────────────────────
function GenerateTab() {
  const [imageFile, setImageFile] = React.useState(null)
  const [preview, setPreview]     = React.useState(null)
  const fileRef = useRef()

  return (
    <div style={{ padding: 8 }}>
      <SectionHeader label="IMG_TO_3D" />
      <p style={{ fontSize: 9, color: 'var(--gf-text-3)', padding: '0 2px 8px',
                  lineHeight: 1.8, fontFamily: 'monospace', letterSpacing: '0.05em' }}>
        // Generate mesh from any photo using<br/>// local AI — Hunyuan3D / TripoSG / TRELLIS
      </p>

      <div onClick={() => fileRef.current?.click()} style={{
        border: `1px dashed ${imageFile ? 'var(--gf-neon)' : 'var(--gf-border-h)'}`,
        borderRadius: 'var(--gf-radius)',
        padding: 14, textAlign: 'center',
        cursor: 'pointer',
        background: imageFile ? 'rgba(57,255,20,0.04)' : 'var(--gf-bg-2)',
        boxShadow: imageFile ? '0 0 10px #39FF1418' : 'none',
        transition: 'all 0.15s', marginBottom: 8,
      }}>
        {preview
          ? <img src={preview} style={{ width: '100%', borderRadius: 3, maxHeight: 110, objectFit: 'cover',
                                        border: '1px solid var(--gf-neon-dim)' }} />
          : <>
              <div style={{ fontSize: 20, marginBottom: 4 }}>📷</div>
              <div style={{ fontSize: 9, color: 'var(--gf-text-3)', fontFamily: 'monospace',
                            letterSpacing: '0.08em' }}>SELECT_REFERENCE_IMAGE</div>
            </>
        }
      </div>
      <input ref={fileRef} type="file" accept="image/*" hidden
             onChange={e => { const f = e.target.files[0]; if (f) { setImageFile(f); setPreview(URL.createObjectURL(f)) }}} />

      <MatrixButton disabled={!imageFile} label="GENERATE_MESH" />

      <div style={{ marginTop: 10 }}>
        <SectionHeader label="AI_MODELS" />
        {['HUNYUAN3D_MINI', 'TRIPOSG', 'TRELLIS_2'].map(m => (
          <div key={m} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '5px 6px', background: 'var(--gf-bg-2)',
            border: '1px solid var(--gf-border)', borderRadius: 'var(--gf-radius-sm)',
            marginBottom: 3, fontSize: 9, fontFamily: 'monospace',
          }}>
            <span style={{ color: 'var(--gf-text-2)', letterSpacing: '0.05em' }}>{m}</span>
            <span style={{ color: 'var(--gf-text-4)', fontSize: 8 }}>NOT_INSTALLED</span>
          </div>
        ))}
      </div>
    </div>
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
