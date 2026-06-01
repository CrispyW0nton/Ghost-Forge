import React, { Suspense, useRef, useState, useEffect, useCallback, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, TransformControls, useGLTF, useProgress, Html } from '@react-three/drei'
import * as THREE from 'three'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import { useSceneStore, useSettingsStore } from '../store'
import MatrixRain from './MatrixRain'

// ─── Neon green Matrix grid ───────────────────────────────────────────────────
function MatrixGrid() {
  return (
    <>
      <gridHelper args={[40, 40, '#39FF14', '#0D2A0D']} position={[0, -0.001, 0]} />
      <gridHelper args={[40, 160, '#061206', '#061206']} position={[0, -0.002, 0]} />
    </>
  )
}

// ─── Glowing XYZ axis lines ───────────────────────────────────────────────────
function NeonAxes() {
  return (
    <group>
      {[
        { color: '#FF2D55', pts: [-4,0,0, 4,0,0] },
        { color: '#39FF14', pts: [0,0,0,  0,4,0] },
        { color: '#00E5FF', pts: [0,0,-4, 0,0,4] },
      ].map(({ color, pts }, i) => (
        <line key={i}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[new Float32Array(pts), 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={color} />
        </line>
      ))}
    </group>
  )
}

// ─── Loading spinner overlay (inside canvas) ─────────────────────────────────
function ModelLoader() {
  const { active, progress } = useProgress()
  if (!active) return null
  return (
    <Html center>
      <div style={{
        color: '#39FF14', fontFamily: 'monospace', fontSize: 11,
        textAlign: 'center', letterSpacing: '0.1em',
        textShadow: '0 0 8px #39FF14',
      }}>
        <div style={{ marginBottom: 6 }}>LOADING MESH…</div>
        <div style={{
          width: 140, height: 2,
          background: 'rgba(57,255,20,0.15)',
          borderRadius: 1, overflow: 'hidden',
        }}>
          <div style={{
            height: '100%', width: `${progress}%`,
            background: 'linear-gradient(90deg, #00CC0A, #39FF14)',
            boxShadow: '0 0 6px #39FF14',
            transition: 'width 0.2s',
          }} />
        </div>
        <div style={{ marginTop: 5, fontSize: 10, opacity: 0.6 }}>{Math.round(progress)}%</div>
      </div>
    </Html>
  )
}

// ─── GLB / GLTF model component ───────────────────────────────────────────────
function GltfModel({ url, onLoaded }) {
  const { scene } = useGLTF(url)
  const groupRef  = useRef()
  const fitted    = useRef(false)

  useEffect(() => {
    if (!scene || fitted.current) return
    fitted.current = true

    // Count verts/faces + apply Matrix lighting tint
    let verts = 0, faces = 0
    scene.traverse(child => {
      if (child.isMesh) {
        child.castShadow    = true
        child.receiveShadow = true
        verts += child.geometry.attributes.position?.count || 0
        faces += child.geometry.index ? child.geometry.index.count / 3
                                      : (child.geometry.attributes.position?.count || 0) / 3
        if (child.material) {
          const mats = Array.isArray(child.material) ? child.material : [child.material]
          mats.forEach(mat => {
            if (!mat.map) {
              mat.emissive          = new THREE.Color('#0A1A0A')
              mat.emissiveIntensity = 0.08
            }
          })
        }
      }
    })

    // Auto-center & scale to fit viewport
    const box    = new THREE.Box3().setFromObject(scene)
    const center = box.getCenter(new THREE.Vector3())
    const size   = box.getSize(new THREE.Vector3())
    const maxDim = Math.max(size.x, size.y, size.z)
    const scale  = maxDim > 0 ? (3.0 / maxDim) : 1
    scene.position.sub(center)
    if (groupRef.current) groupRef.current.scale.setScalar(scale)

    onLoaded?.({ vertices: Math.round(verts), faces: Math.round(faces) })
  }, [scene])

  return <group ref={groupRef}><primitive object={scene} /></group>
}

// ─── GLB from a File object — stable blob URL, revoked on unmount ─────────────
function GltfModelFromFile({ file, onLoaded }) {
  const [url, setUrl] = useState(null)

  useEffect(() => {
    const blobUrl = URL.createObjectURL(file)
    setUrl(blobUrl)
    return () => URL.revokeObjectURL(blobUrl)
  }, [file])

  if (!url) return null
  return (
    <Suspense fallback={<ModelLoader />}>
      <GltfModel url={url} onLoaded={onLoaded} />
    </Suspense>
  )
}

// ─── OBJ model component ──────────────────────────────────────────────────────
function ObjModel({ file, onLoaded }) {
  const [group, setGroup] = useState(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    const loader = new OBJLoader()
    const url = URL.createObjectURL(file)

    loader.load(url, (obj) => {
      if (!mountedRef.current) return
      URL.revokeObjectURL(url)

      // Auto-center
      const box = new THREE.Box3().setFromObject(obj)
      const center = box.getCenter(new THREE.Vector3())
      const size = box.getSize(new THREE.Vector3())
      const maxDim = Math.max(size.x, size.y, size.z)
      const scale = maxDim > 0 ? (3.0 / maxDim) : 1
      obj.position.sub(center.multiplyScalar(scale))
      obj.scale.setScalar(scale)

      // Apply Matrix material
      let vCount = 0, fCount = 0
      obj.traverse(child => {
        if (child.isMesh) {
          vCount += child.geometry.attributes.position?.count || 0
          fCount += (child.geometry.index ? child.geometry.index.count / 3 : 0)
          child.material = new THREE.MeshStandardMaterial({
            color: '#1A2A1A',
            emissive: '#39FF14',
            emissiveIntensity: 0.06,
            roughness: 0.7,
            metalness: 0.3,
            wireframe: false,
          })
        }
      })
      setGroup(obj)
      onLoaded?.({ vertices: vCount, faces: fCount })
    })

    return () => {
      mountedRef.current = false
    }
  }, [file])

  if (!group) return null
  return <primitive object={group} />
}

// ─── STL model component ──────────────────────────────────────────────────────
function StlModel({ file, onLoaded }) {
  const [mesh, setMesh] = useState(null)

  useEffect(() => {
    const loader = new STLLoader()
    const url = URL.createObjectURL(file)
    loader.load(url, (geometry) => {
      URL.revokeObjectURL(url)
      geometry.computeVertexNormals()
      const box = new THREE.Box3().setFromBufferAttribute(geometry.attributes.position)
      const center = box.getCenter(new THREE.Vector3())
      const size = box.getSize(new THREE.Vector3())
      const maxDim = Math.max(size.x, size.y, size.z)
      const scale = maxDim > 0 ? (3.0 / maxDim) : 1
      geometry.translate(-center.x, -center.y, -center.z)
      const mat = new THREE.MeshStandardMaterial({
        color: '#0A1A0A', emissive: '#39FF14', emissiveIntensity: 0.08,
        roughness: 0.6, metalness: 0.4,
      })
      const m = new THREE.Mesh(geometry, mat)
      m.scale.setScalar(scale)
      setMesh(m)
      onLoaded?.({ vertices: geometry.attributes.position.count, faces: geometry.attributes.position.count / 3 })
    })
  }, [file])

  if (!mesh) return null
  return <primitive object={mesh} />
}

// ─── PLY model component ──────────────────────────────────────────────────────
function PlyModel({ file, onLoaded }) {
  const [mesh, setMesh] = useState(null)

  useEffect(() => {
    const loader = new PLYLoader()
    const url = URL.createObjectURL(file)
    loader.load(url, (geometry) => {
      URL.revokeObjectURL(url)
      geometry.computeVertexNormals()
      const box = new THREE.Box3().setFromBufferAttribute(geometry.attributes.position)
      const center = box.getCenter(new THREE.Vector3())
      const size = box.getSize(new THREE.Vector3())
      const maxDim = Math.max(size.x, size.y, size.z)
      const scale = maxDim > 0 ? (3.0 / maxDim) : 1
      geometry.translate(-center.x, -center.y, -center.z)
      const mat = new THREE.MeshStandardMaterial({
        color: '#0A1A0A', emissive: '#39FF14', emissiveIntensity: 0.08,
        roughness: 0.6, metalness: 0.4, vertexColors: geometry.hasAttribute('color'),
      })
      const m = new THREE.Mesh(geometry, mat)
      m.scale.setScalar(scale)
      setMesh(m)
      onLoaded?.({ vertices: geometry.attributes.position.count, faces: geometry.attributes.position.count / 3 })
    })
  }, [file])

  if (!mesh) return null
  return <primitive object={mesh} />
}

// ─── Transform gizmo for the selected scene object ───────────────────────────
//
// Wraps the target group in a drei <TransformControls>. On drag end we
// snapshot translate/rotate/scale and call writeTransformToGraph on the
// scene store, which (a) updates the local object record and (b) writes
// the values into the object's bound EditGraph so the same edit shows up
// in the MODS tab.
function TransformGizmo({ target, objectId }) {
  const controlsRef = useRef()
  const orbit = useThree(state => state.controls)
  const transformMode = useSceneStore(s => s.transformMode)
  const transformSpace = useSceneStore(s => s.transformSpace)
  const writeTransformToGraph = useSceneStore(s => s.writeTransformToGraph)

  // Disable orbit while dragging the gizmo so the camera doesn't tumble.
  useEffect(() => {
    const tc = controlsRef.current
    if (!tc) return
    const onDragChange = (event) => {
      if (orbit) orbit.enabled = !event.value
    }
    const onObjectChange = () => {
      if (!target.current) return
      const t = target.current
      const translate = [t.position.x, t.position.y, t.position.z]
      const rotate_euler_deg = [
        THREE.MathUtils.radToDeg(t.rotation.x),
        THREE.MathUtils.radToDeg(t.rotation.y),
        THREE.MathUtils.radToDeg(t.rotation.z),
      ]
      const scaleArr = [t.scale.x, t.scale.y, t.scale.z]
      const uniform = scaleArr[0] === scaleArr[1] && scaleArr[1] === scaleArr[2]
      const transform = {
        translate,
        rotate_euler_deg,
        scale: uniform ? scaleArr[0] : scaleArr,
      }
      writeTransformToGraph(objectId, transform)
    }
    tc.addEventListener('dragging-changed', onDragChange)
    tc.addEventListener('mouseUp', onObjectChange)
    return () => {
      tc.removeEventListener('dragging-changed', onDragChange)
      tc.removeEventListener('mouseUp', onObjectChange)
    }
  }, [orbit, target, objectId, writeTransformToGraph])

  if (!target.current || !transformMode) return null
  return (
    <TransformControls
      ref={controlsRef}
      object={target.current}
      mode={transformMode}
      space={transformSpace}
      size={0.8}
    />
  )
}


// ─── Universal scene object dispatcher ───────────────────────────────────────
function SceneObject({ obj }) {
  const { updateObject, selectedIds, selectObject } = useSceneStore()
  const groupRef = useRef()
  const isSelected = selectedIds.includes(obj.id)
  if (!obj.visible) return null

  const handleLoaded = useCallback((stats) => {
    if (stats && (stats.vertices || stats.faces)) {
      updateObject(obj.id, { meshStats: stats })
    }
  }, [obj.id])

  // Apply any transform stashed on the object (e.g. from a previous gizmo
  // drag, or the initial values pulled from a bound graph). The gizmo
  // updates the live three object directly; this keeps state durable
  // when objects unmount and remount (e.g. after a job completes).
  useEffect(() => {
    const g = groupRef.current
    if (!g || !obj.transform) return
    const t = obj.transform
    if (Array.isArray(t.translate)) {
      g.position.set(t.translate[0] || 0, t.translate[1] || 0, t.translate[2] || 0)
    }
    if (Array.isArray(t.rotate_euler_deg)) {
      g.rotation.set(
        THREE.MathUtils.degToRad(t.rotate_euler_deg[0] || 0),
        THREE.MathUtils.degToRad(t.rotate_euler_deg[1] || 0),
        THREE.MathUtils.degToRad(t.rotate_euler_deg[2] || 0),
      )
    }
    if (typeof t.scale === 'number') {
      g.scale.setScalar(t.scale)
    } else if (Array.isArray(t.scale)) {
      g.scale.set(t.scale[0] || 1, t.scale[1] || 1, t.scale[2] || 1)
    }
  }, [obj.transform])

  const handlePointerDown = useCallback((e) => {
    e.stopPropagation()
    selectObject(obj.id, e.shiftKey)
  }, [obj.id, selectObject])

  // Render the appropriate model into a wrapper group that the gizmo can
  // attach to. The wrapper carries the position/rotation/scale we'll
  // ultimately push into the modifier graph.
  let body = null
  if (obj.previewUrl) {
    body = (
      <Suspense fallback={<ModelLoader />}>
        <GltfModel url={obj.previewUrl} onLoaded={handleLoaded} />
      </Suspense>
    )
  } else if (!obj.file) {
    body = (
      <>
        <mesh>
          <boxGeometry args={[1,1,1]} />
          <meshStandardMaterial color="#0A1A0A" emissive="#39FF14" emissiveIntensity={0.08} roughness={0.7} metalness={0.4} />
        </mesh>
        <mesh>
          <boxGeometry args={[1.003,1.003,1.003]} />
          <meshBasicMaterial color="#39FF14" wireframe opacity={0.5} transparent />
        </mesh>
      </>
    )
  } else {
    const ext = obj.file.name?.split('.').pop().toLowerCase()
    if (ext === 'glb' || ext === 'gltf') {
      body = <GltfModelFromFile file={obj.file} onLoaded={handleLoaded} />
    } else if (ext === 'obj') {
      body = <ObjModel file={obj.file} onLoaded={handleLoaded} />
    } else if (ext === 'stl') {
      body = <StlModel file={obj.file} onLoaded={handleLoaded} />
    } else if (ext === 'ply') {
      body = <PlyModel file={obj.file} onLoaded={handleLoaded} />
    } else {
      body = (
        <mesh>
          <boxGeometry args={[1,1,1]} />
          <meshStandardMaterial color="#1A0A0A" emissive="#FF2D55" emissiveIntensity={0.1} />
        </mesh>
      )
    }
  }

  return (
    <>
      <group ref={groupRef} onPointerDown={handlePointerDown}>
        {body}
        {isSelected && (
          <mesh>
            <boxGeometry args={[1.05, 1.05, 1.05]} />
            <meshBasicMaterial color="#39FF14" wireframe opacity={0.35} transparent />
          </mesh>
        )}
      </group>
      {isSelected && <TransformGizmo target={groupRef} objectId={obj.id} />}
    </>
  )
}

// ─── Empty scene overlay ──────────────────────────────────────────────────────
function EmptySceneOverlay({ show }) {
  if (!show) return null
  return (
    <div style={{
      position: 'absolute', inset: 0,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      pointerEvents: 'none', gap: 18, zIndex: 5,
    }}>
      <svg width="88" height="88" viewBox="0 0 32 32" fill="none" opacity={0.1}>
        <path d="M4 30 L4 16 C4 8 9 3 16 3 C23 3 28 8 28 16 L28 30 L24 27 L20 30 L16 27 L12 30 L8 27 Z"
              fill="none" stroke="#39FF14" strokeWidth="0.5"/>
        <ellipse cx="12.5" cy="17" rx="2.4" ry="1.8" fill="#39FF14"/>
        <ellipse cx="19.5" cy="17" rx="2.4" ry="1.8" fill="#39FF14"/>
      </svg>
      <div style={{ textAlign: 'center', lineHeight: 2.3, fontFamily: 'monospace' }}>
        {[
          ['IMPORT_MODEL',   '// Scene panel → Import'],
          ['GENERATE_MESH',  '// GEN_3D tab → photo'],
          ['ASK_GHOST_AI',   '// Chat panel'],
        ].map(([cmd, hint]) => (
          <div key={cmd} style={{ fontSize: 10 }}>
            <span style={{ color: '#39FF1440' }}>&gt; </span>
            <span style={{ color: '#39FF1455', letterSpacing: '0.12em' }}>{cmd}</span>
            <span style={{ color: '#245924', marginLeft: 8, fontSize: 9 }}>{hint}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Job progress HUD ─────────────────────────────────────────────────────────
function JobHUD({ job }) {
  if (!job || job.status === 'done') return null
  return (
    <div style={{
      position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
      background: 'rgba(1,3,1,0.94)',
      border: '1px solid var(--gf-neon-dim)',
      borderRadius: 'var(--gf-radius)',
      padding: '9px 16px',
      display: 'flex', alignItems: 'center', gap: 12,
      boxShadow: '0 0 20px #39FF1422, 0 6px 24px rgba(0,0,0,0.7)',
      minWidth: 280, zIndex: 10,
    }}>
      <div className="animate-spin" style={{
        width: 14, height: 14, flexShrink: 0,
        border: '2px solid rgba(57,255,20,0.15)', borderTopColor: 'var(--gf-neon)',
        borderRadius: '50%', boxShadow: '0 0 6px var(--gf-neon)',
      }}/>
      <div style={{ flex: 1 }}>
        <div style={{
          fontSize: 9, color: 'var(--gf-text-2)', fontFamily: 'monospace',
          letterSpacing: '0.1em', marginBottom: 5, textTransform: 'uppercase',
        }}>
          <span style={{ color: 'var(--gf-neon)', marginRight: 4 }}>&gt;&gt;</span>
          {job.stage || 'PROCESSING'}
        </div>
        <div style={{ height: 2, background: 'rgba(57,255,20,0.1)', borderRadius: 1, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${job.progress || 0}%`,
            background: 'linear-gradient(90deg, var(--gf-neon-dim), var(--gf-neon), var(--gf-neon-bright))',
            boxShadow: '0 0 6px var(--gf-neon)', borderRadius: 1, transition: 'width 0.4s ease',
          }}/>
        </div>
      </div>
      <span style={{
        fontSize: 12, color: 'var(--gf-neon)', fontFamily: 'monospace', fontWeight: 700,
        textShadow: '0 0 8px var(--gf-neon)', flexShrink: 0,
      }}>
        {job.progress || 0}%
      </span>
    </div>
  )
}

// ─── Camera preset buttons (top right) ───────────────────────────────────────
function CameraPresets({ orbitRef }) {
  const [active, setActive] = useState('PERSP')
  const { camera } = useThree()
  const presets = {
    PERSP: [3, 2.5, 4],
    FRONT: [0, 0, 5],
    SIDE:  [5, 0, 0],
    TOP:   [0, 6, 0.001],
  }
  const goTo = (name) => {
    setActive(name)
    camera.position.set(...presets[name])
    orbitRef.current?.target.set(0, 0, 0)
    orbitRef.current?.update()
  }
  return (
    <Html style={{ position: 'absolute', top: 10, right: 10 }} prepend>
      <div style={{ display: 'flex', gap: 3 }}>
        {Object.keys(presets).map(name => (
          <button key={name} onClick={() => goTo(name)} style={{
            padding: '3px 8px', fontSize: 8, fontFamily: 'monospace', letterSpacing: '0.1em',
            background: active === name ? 'rgba(57,255,20,0.1)' : 'rgba(1,3,1,0.85)',
            border: `1px solid ${active === name ? '#00CC0A' : '#0C200C'}`,
            borderRadius: 2,
            color: active === name ? '#39FF14' : '#245924',
            cursor: 'pointer', backdropFilter: 'blur(4px)',
            textShadow: active === name ? '0 0 5px #39FF14' : 'none',
            boxShadow: active === name ? '0 0 8px #39FF1425' : 'none',
            transition: 'all 0.1s',
          }}>{name}</button>
        ))}
      </div>
    </Html>
  )
}

// ─── Gizmo mode pills (top right, under camera presets) ──────────────────────
function GizmoModeBar() {
  const transformMode = useSceneStore(s => s.transformMode)
  const setTransformMode = useSceneStore(s => s.setTransformMode)
  const transformSpace = useSceneStore(s => s.transformSpace)
  const setTransformSpace = useSceneStore(s => s.setTransformSpace)
  const selectedIds = useSceneStore(s => s.selectedIds)
  if (selectedIds.length === 0) return null
  const modes = [
    ['T', 'translate'],
    ['R', 'rotate'],
    ['S', 'scale'],
    ['—', null],
  ]
  return (
    <Html style={{ position: 'absolute', top: 36, right: 10 }} prepend>
      <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
        {modes.map(([label, m]) => {
          const active = transformMode === m
          return (
            <button key={label} onClick={() => setTransformMode(m)} style={{
              padding: '3px 8px', fontSize: 8, fontFamily: 'monospace', letterSpacing: '0.1em',
              background: active ? 'rgba(57,255,20,0.1)' : 'rgba(1,3,1,0.85)',
              border: `1px solid ${active ? '#00CC0A' : '#0C200C'}`,
              borderRadius: 2,
              color: active ? '#39FF14' : '#245924',
              cursor: 'pointer',
              textShadow: active ? '0 0 5px #39FF14' : 'none',
              boxShadow: active ? '0 0 8px #39FF1425' : 'none',
            }}>{label}</button>
          )
        })}
        <button onClick={() => setTransformSpace(transformSpace === 'world' ? 'local' : 'world')} style={{
          padding: '3px 8px', fontSize: 8, fontFamily: 'monospace', letterSpacing: '0.1em',
          background: 'rgba(1,3,1,0.85)', border: '1px solid #0C200C', borderRadius: 2,
          color: '#39FF14', cursor: 'pointer', marginLeft: 4,
        }}>{transformSpace.toUpperCase()}</button>
      </div>
    </Html>
  )
}

// ─── View mode label (top left) ───────────────────────────────────────────────
function ViewportHUD({ mode }) {
  const labels = { '3d': 'PERSPECTIVE_VIEW', 'uv': 'UV_EDITOR', 'texture': 'TEXTURE_PAINT' }
  return (
    <div style={{
      position: 'absolute', top: 10, left: 10, zIndex: 10,
      display: 'flex', alignItems: 'center', gap: 6,
      background: 'rgba(1,3,1,0.85)', border: '1px solid #0C200C',
      borderRadius: 2, padding: '3px 9px',
      backdropFilter: 'blur(4px)', pointerEvents: 'none',
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: '50%',
        background: '#39FF14', boxShadow: '0 0 5px #39FF14',
        animation: 'pulse 3s ease infinite', flexShrink: 0,
      }}/>
      <span style={{ fontSize: 8, color: '#245924', fontFamily: 'monospace', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
        {labels[mode] || 'VIEWPORT'}
      </span>
    </div>
  )
}

// ─── Live camera coordinate readout (bottom left) ────────────────────────────
function CoordHUD() {
  const [pos, setPos] = useState([0, 0, 0])
  const { camera } = useThree()
  useFrame(() => setPos([camera.position.x.toFixed(2), camera.position.y.toFixed(2), camera.position.z.toFixed(2)]))
  return (
    <Html style={{ position: 'absolute', bottom: 10, left: 10 }} prepend>
      <div style={{
        background: 'rgba(1,3,1,0.75)', border: '1px solid #0C200C', borderRadius: 2,
        padding: '3px 8px', fontFamily: 'monospace', fontSize: 8, letterSpacing: '0.08em',
        pointerEvents: 'none', whiteSpace: 'nowrap',
      }}>
        <span style={{ color: '#FF2D55' }}>X</span><span style={{ color: '#245924', margin: '0 4px' }}>{pos[0]}</span>
        <span style={{ color: '#39FF14' }}>Y</span><span style={{ color: '#245924', margin: '0 4px' }}>{pos[1]}</span>
        <span style={{ color: '#00E5FF' }}>Z</span><span style={{ color: '#245924', marginLeft: 4 }}>{pos[2]}</span>
      </div>
    </Html>
  )
}

// ─── Scene content (inside Canvas) ───────────────────────────────────────────
function SceneContent({ objects, viewportGrid, viewportWireframe, orbitRef }) {
  return (
    <>
      <ambientLight intensity={0.3} color="#1A3B1A" />
      <pointLight position={[0, 6, 0]}    intensity={1.5} color="#39FF14" distance={30} />
      <pointLight position={[5, 3, 5]}    intensity={0.7} color="#00E5FF" distance={20} />
      <pointLight position={[-5, -2, -5]} intensity={0.3} color="#39FF14" distance={15} />

      {viewportGrid && <MatrixGrid />}
      <NeonAxes />

      <Suspense fallback={<ModelLoader />}>
        {objects.map(obj => (
          // key includes previewUrl so Three.js re-mounts fully when job completes
          <SceneObject key={`${obj.id}_${obj.previewUrl || 'raw'}`} obj={obj} />
        ))}
      </Suspense>

      <OrbitControls
        ref={orbitRef}
        makeDefault
        enableDamping dampingFactor={0.05}
        minDistance={0.1} maxDistance={200}
        screenSpacePanning={false}
      />
      <CameraPresets orbitRef={orbitRef} />
      <GizmoModeBar />
      <CoordHUD />
    </>
  )
}

// ─── Main Viewport ────────────────────────────────────────────────────────────
export default function Viewport() {
  const { objects, activeJob, viewportMode } = useSceneStore()
  const { viewportGrid, viewportWireframe } = useSettingsStore()
  const orbitRef = useRef()
  const isEmpty  = objects.length === 0

  return (
    <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#010301' }}>
      <MatrixRain opacity={0.05} fontSize={12} speed={0.65} />
      <ViewportHUD mode={viewportMode} />

      <Canvas
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 1 }}
        camera={{ position: [3, 2.5, 4], fov: 45, near: 0.01, far: 2000 }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl }) => {
          gl.setClearColor(new THREE.Color('#010301'), 0)
          gl.setPixelRatio(Math.min(window.devicePixelRatio, 2))
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.15
        }}
      >
        <SceneContent
          objects={objects}
          viewportGrid={viewportGrid}
          viewportWireframe={viewportWireframe}
          orbitRef={orbitRef}
        />
      </Canvas>

      <EmptySceneOverlay show={isEmpty} />
      <JobHUD job={activeJob} />

      {/* CRT vignette */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none',
        background: 'radial-gradient(ellipse at center, transparent 45%, rgba(1,3,1,0.65) 100%)',
      }}/>

      {/* Corner bracket decorations */}
      {[[{top:8,left:8},0],[{top:8,right:8},90],[{bottom:8,right:8},180],[{bottom:8,left:8},270]].map(([pos,rot],i) => (
        <svg key={i} width="14" height="14" viewBox="0 0 14 14" fill="none"
             style={{ position:'absolute', zIndex:3, pointerEvents:'none', opacity:0.3, transform:`rotate(${rot}deg)`, ...pos }}>
          <path d="M1 8 L1 1 L8 1" stroke="#39FF14" strokeWidth="1.2" fill="none"/>
        </svg>
      ))}
    </div>
  )
}
