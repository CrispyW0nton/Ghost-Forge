import React, { Suspense, useRef, useEffect, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Grid, Environment, useGLTF, Center, Bounds } from '@react-three/drei'
import * as THREE from 'three'
import { useSceneStore, useSettingsStore } from '../store'

// ─── Loaded model component ───────────────────────────────────────────────────
function SceneObject({ obj }) {
  const [gltf, setGltf] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!obj.file) return
    const url = URL.createObjectURL(obj.file)
    // Use Three.js loaders based on file extension
    const ext = obj.file.name.split('.').pop().toLowerCase()

    if (ext === 'glb' || ext === 'gltf') {
      const { GLTFLoader } = require('three/examples/jsm/loaders/GLTFLoader')
      const loader = new GLTFLoader()
      loader.load(url, (g) => {
        setGltf(g.scene)
        URL.revokeObjectURL(url)
      }, undefined, setError)
    }
    // OBJ/STL/PLY would need their respective loaders
    // For now show a placeholder geometry
    return () => URL.revokeObjectURL(url)
  }, [obj.file])

  if (!obj.visible) return null

  // Default: show a box placeholder if model not loaded yet
  return (
    <group>
      <mesh>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          color="#6366f1"
          wireframe={false}
          roughness={0.7}
          metalness={0.1}
        />
      </mesh>
    </group>
  )
}

// ─── Grid floor ───────────────────────────────────────────────────────────────
function SceneGrid() {
  return (
    <gridHelper
      args={[20, 20, '#252538', '#1a1a2a']}
      position={[0, -0.01, 0]}
    />
  )
}

// ─── Axis indicator ───────────────────────────────────────────────────────────
function AxisHelper() {
  return <axesHelper args={[1.5]} />
}

// ─── Empty scene prompt ───────────────────────────────────────────────────────
function EmptySceneOverlay({ show }) {
  if (!show) return null
  return (
    <div style={{
      position: 'absolute', inset: 0,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      pointerEvents: 'none', gap: 12,
    }}>
      <svg width="64" height="64" viewBox="0 0 32 32" fill="none" opacity={0.15}>
        <path d="M16 4 L28 10 L28 22 L16 28 L4 22 L4 10 Z"
              stroke="var(--gf-text)" strokeWidth="1.5" fill="none"/>
        <path d="M4 10 L16 16 L28 10" stroke="var(--gf-text)" strokeWidth="1.5"/>
        <line x1="16" y1="16" x2="16" y2="28" stroke="var(--gf-text)" strokeWidth="1.5"/>
      </svg>
      <p style={{ color: 'var(--gf-text-3)', fontSize: 13, textAlign: 'center', lineHeight: 1.8 }}>
        Import a model from the <strong style={{ color: 'var(--gf-text-2)' }}>Scene</strong> panel<br/>
        or ask your <strong style={{ color: 'var(--gf-forge)' }}>AI</strong> to generate one
      </p>
    </div>
  )
}

// ─── Job progress overlay ─────────────────────────────────────────────────────
function JobOverlay({ job }) {
  if (!job || job.status === 'done') return null
  return (
    <div style={{
      position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
      background: 'var(--gf-bg-2)', border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius)', padding: '10px 16px',
      display: 'flex', alignItems: 'center', gap: 10,
      boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
      minWidth: 260,
    }}>
      <div className="animate-spin" style={{
        width: 14, height: 14,
        border: '2px solid var(--gf-border)',
        borderTopColor: 'var(--gf-forge)',
        borderRadius: '50%', flexShrink: 0,
      }}/>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 12, color: 'var(--gf-text-2)', marginBottom: 4 }}>
          {job.stage || 'Processing…'}
        </div>
        <div style={{ height: 3, background: 'var(--gf-bg-3)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${job.progress || 0}%`,
            background: 'linear-gradient(90deg, var(--gf-forge), #ff9a5c)',
            borderRadius: 2, transition: 'width 0.4s ease',
          }}/>
        </div>
      </div>
      <span style={{ fontSize: 11, color: 'var(--gf-text-3)', flexShrink: 0 }}>
        {job.progress || 0}%
      </span>
    </div>
  )
}

// ─── Main Viewport ────────────────────────────────────────────────────────────
export default function Viewport() {
  const { objects, activeJob, viewportMode } = useSceneStore()
  const { viewportGrid } = useSettingsStore()

  const isEmpty = objects.length === 0

  return (
    <div style={{ flex: 1, position: 'relative', background: 'var(--gf-bg-base)', overflow: 'hidden' }}>

      {/* View mode label */}
      <div style={{
        position: 'absolute', top: 10, left: 10, zIndex: 10,
        background: 'rgba(10,10,15,0.7)',
        border: '1px solid var(--gf-border)',
        borderRadius: 'var(--gf-radius-sm)',
        padding: '3px 8px', fontSize: 11,
        color: 'var(--gf-text-3)',
        backdropFilter: 'blur(4px)',
        pointerEvents: 'none',
      }}>
        {viewportMode === '3d' ? 'Perspective' : viewportMode === 'uv' ? 'UV Editor' : 'Texture Paint'}
      </div>

      {/* Camera preset buttons */}
      <CameraPresets />

      {/* Three.js canvas */}
      <Canvas
        style={{ width: '100%', height: '100%' }}
        camera={{ position: [3, 2.5, 4], fov: 45, near: 0.01, far: 1000 }}
        gl={{ antialias: true, alpha: false }}
        onCreated={({ gl }) => {
          gl.setClearColor(new THREE.Color('#0a0a0f'))
          gl.setPixelRatio(Math.min(window.devicePixelRatio, 2))
        }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 8, 5]} intensity={0.8} castShadow />
        <directionalLight position={[-5, -3, -5]} intensity={0.2} color="#8080ff" />
        <pointLight position={[0, 4, 0]} intensity={0.3} color="#ff6b2b" />

        {viewportGrid && <SceneGrid />}
        <AxisHelper />

        <Suspense fallback={null}>
          {objects.map(obj => <SceneObject key={obj.id} obj={obj} />)}
        </Suspense>

        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.05}
          minDistance={0.5}
          maxDistance={100}
        />
      </Canvas>

      {/* Overlays */}
      <EmptySceneOverlay show={isEmpty} />
      <JobOverlay job={activeJob} />
    </div>
  )
}

// ─── Camera preset buttons ────────────────────────────────────────────────────
function CameraPresets() {
  const presets = [
    { label: 'Persp', key: 'persp' },
    { label: 'Front', key: 'front' },
    { label: 'Side',  key: 'side'  },
    { label: 'Top',   key: 'top'   },
  ]
  const [active, setActive] = React.useState('persp')

  return (
    <div style={{
      position: 'absolute', top: 10, right: 10, zIndex: 10,
      display: 'flex', gap: 3,
    }}>
      {presets.map(p => (
        <button key={p.key} onClick={() => setActive(p.key)} style={{
          padding: '3px 8px', fontSize: 10,
          background: active === p.key ? 'var(--gf-bg-3)' : 'rgba(10,10,15,0.7)',
          border: `1px solid ${active === p.key ? 'var(--gf-border-h)' : 'var(--gf-border)'}`,
          borderRadius: 'var(--gf-radius-sm)',
          color: active === p.key ? 'var(--gf-text)' : 'var(--gf-text-3)',
          cursor: 'pointer', backdropFilter: 'blur(4px)',
          transition: 'all 0.15s',
        }}>
          {p.label}
        </button>
      ))}
    </div>
  )
}
