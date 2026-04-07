import React, { Suspense, useRef, useState, useEffect, useCallback } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { useSceneStore, useSettingsStore } from '../store'
import MatrixRain from './MatrixRain'

// ─── Neon green Matrix grid ───────────────────────────────────────────────────
function MatrixGrid() {
  return (
    <>
      {/* Primary grid — bright neon green lines */}
      <gridHelper
        args={[40, 40, '#39FF14', '#0D2A0D']}
        position={[0, -0.001, 0]}
      />
      {/* Fine sub-grid — very dim */}
      <gridHelper
        args={[40, 160, '#061206', '#061206']}
        position={[0, -0.002, 0]}
      />
    </>
  )
}

// ─── Glowing XYZ axis lines ────────────────────────────────────────────────
function NeonAxes() {
  const axisData = [
    { color: '#FF2D55', points: [-4, 0, 0, 4, 0, 0] },   // X — red/danger
    { color: '#39FF14', points: [0, 0, 0, 0, 4, 0] },     // Y — neon green
    { color: '#00E5FF', points: [0, 0, -4, 0, 0, 4] },    // Z — cyan
  ]
  return (
    <group>
      {axisData.map(({ color, points }, i) => (
        <line key={i}>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              args={[new Float32Array(points), 3]}
            />
          </bufferGeometry>
          <lineBasicMaterial color={color} linewidth={2} />
        </line>
      ))}
    </group>
  )
}

// ─── Animated neon wireframe placeholder ──────────────────────────────────────
function SceneObject({ obj }) {
  const meshRef = useRef()
  if (!obj.visible) return null

  return (
    <group>
      {/* Solid mesh */}
      <mesh ref={meshRef}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial
          color="#0A1A0A"
          emissive="#39FF14"
          emissiveIntensity={0.08}
          roughness={0.7}
          metalness={0.4}
        />
      </mesh>
      {/* Wireframe overlay — neon */}
      <mesh>
        <boxGeometry args={[1.002, 1.002, 1.002]} />
        <meshBasicMaterial color="#39FF14" wireframe opacity={0.6} transparent />
      </mesh>
    </group>
  )
}

// ─── Empty scene prompt overlay ───────────────────────────────────────────────
function EmptySceneOverlay({ show }) {
  if (!show) return null
  return (
    <div style={{
      position: 'absolute', inset: 0,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      pointerEvents: 'none', gap: 18, zIndex: 5,
    }}>
      {/* Ghost SVG — large, dim */}
      <svg width="90" height="90" viewBox="0 0 32 32" fill="none" opacity={0.12}>
        <path d="M4 30 L4 16 C4 8 9 3 16 3 C23 3 28 8 28 16 L28 30 L24 27 L20 30 L16 27 L12 30 L8 27 Z"
              fill="none" stroke="#39FF14" strokeWidth="0.5"/>
        <ellipse cx="12.5" cy="17" rx="2.4" ry="1.8" fill="#39FF14"/>
        <ellipse cx="19.5" cy="17" rx="2.4" ry="1.8" fill="#39FF14"/>
      </svg>

      <div style={{
        textAlign: 'center', lineHeight: 2.2,
        fontFamily: 'monospace',
      }}>
        {[
          ['IMPORT_MODEL',   '// scene panel (left)'],
          ['GENERATE_MESH',  '// GEN_3D tab → photo → mesh'],
          ['ASK_GHOST_AI',   '// chat panel (right)'],
        ].map(([cmd, hint]) => (
          <div key={cmd} style={{ fontSize: 10 }}>
            <span style={{ color: '#39FF1440' }}>&gt; </span>
            <span style={{ color: '#39FF1450', letterSpacing: '0.12em' }}>{cmd}</span>
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
      position: 'absolute', bottom: 16, left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(1,3,1,0.93)',
      border: '1px solid var(--gf-neon-dim)',
      borderRadius: 'var(--gf-radius)',
      padding: '9px 16px',
      display: 'flex', alignItems: 'center', gap: 12,
      boxShadow: '0 0 20px #39FF1422, 0 6px 24px rgba(0,0,0,0.7)',
      minWidth: 280, zIndex: 10,
    }}>
      {/* Spinner */}
      <div className="animate-spin" style={{
        width: 14, height: 14, flexShrink: 0,
        border: '2px solid rgba(57,255,20,0.15)',
        borderTopColor: 'var(--gf-neon)',
        borderRadius: '50%',
        boxShadow: '0 0 6px var(--gf-neon)',
      }}/>
      <div style={{ flex: 1 }}>
        {/* Stage label */}
        <div style={{
          fontSize: 9, color: 'var(--gf-text-2)',
          fontFamily: 'monospace', letterSpacing: '0.1em',
          marginBottom: 5, textTransform: 'uppercase',
        }}>
          <span style={{ color: 'var(--gf-neon)', marginRight: 4 }}>&gt;&gt;</span>
          {job.stage || 'PROCESSING'}
        </div>
        {/* Progress bar */}
        <div style={{
          height: 2, background: 'rgba(57,255,20,0.1)',
          borderRadius: 1, overflow: 'hidden',
        }}>
          <div style={{
            height: '100%',
            width: `${job.progress || 0}%`,
            background: 'linear-gradient(90deg, var(--gf-neon-dim), var(--gf-neon), var(--gf-neon-bright))',
            boxShadow: '0 0 6px var(--gf-neon)',
            borderRadius: 1,
            transition: 'width 0.4s ease',
          }}/>
        </div>
      </div>
      <span style={{
        fontSize: 12, color: 'var(--gf-neon)',
        fontFamily: 'monospace', fontWeight: 700,
        textShadow: '0 0 8px var(--gf-neon)',
        flexShrink: 0,
      }}>
        {job.progress || 0}%
      </span>
    </div>
  )
}

// ─── Camera preset HUD (top-right) ───────────────────────────────────────────
function CameraPresets({ orbitRef }) {
  const [active, setActive] = useState('PERSP')
  const { camera } = useThree()

  const presets = {
    PERSP: { pos: [3, 2.5, 4],  up: [0, 1, 0] },
    FRONT: { pos: [0, 0, 5],    up: [0, 1, 0] },
    SIDE:  { pos: [5, 0, 0],    up: [0, 1, 0] },
    TOP:   { pos: [0, 5, 0],    up: [0, 0, -1] },
  }

  const goTo = (name) => {
    setActive(name)
    const p = presets[name]
    camera.position.set(...p.pos)
    camera.up.set(...p.up)
    if (orbitRef.current) {
      orbitRef.current.target.set(0, 0, 0)
      orbitRef.current.update()
    }
  }

  return (
    <div style={{
      position: 'absolute', top: 10, right: 10, zIndex: 10,
      display: 'flex', gap: 3,
    }}>
      {Object.keys(presets).map(name => (
        <button key={name} onClick={() => goTo(name)} style={{
          padding: '3px 8px', fontSize: 8,
          fontFamily: 'monospace', letterSpacing: '0.1em',
          background: active === name ? 'rgba(57,255,20,0.1)' : 'rgba(1,3,1,0.85)',
          border: `1px solid ${active === name ? 'var(--gf-neon-dim)' : 'var(--gf-border)'}`,
          borderRadius: 'var(--gf-radius-sm)',
          color: active === name ? 'var(--gf-neon)' : 'var(--gf-text-3)',
          cursor: 'pointer',
          textShadow: active === name ? '0 0 5px var(--gf-neon)' : 'none',
          boxShadow: active === name ? '0 0 8px #39FF1425' : 'none',
          transition: 'all 0.1s',
          backdropFilter: 'blur(4px)',
        }}>
          {name}
        </button>
      ))}
    </div>
  )
}

// ─── Camera orbit controls wrapper that exposes ref ───────────────────────────
function Controls({ orbitRef }) {
  return (
    <OrbitControls
      ref={orbitRef}
      makeDefault
      enableDamping
      dampingFactor={0.05}
      minDistance={0.3}
      maxDistance={120}
      screenSpacePanning={false}
    />
  )
}

// ─── View mode label (top-left HUD) ──────────────────────────────────────────
function ViewportHUD({ mode }) {
  const labels = {
    '3d':      'PERSPECTIVE_VIEW',
    'uv':      'UV_EDITOR',
    'texture': 'TEXTURE_PAINT',
  }
  return (
    <div style={{
      position: 'absolute', top: 10, left: 10, zIndex: 10,
      display: 'flex', alignItems: 'center', gap: 6,
      background: 'rgba(1,3,1,0.85)',
      border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius-sm)',
      padding: '3px 9px',
      backdropFilter: 'blur(4px)',
      pointerEvents: 'none',
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: '50%',
        background: 'var(--gf-neon)',
        boxShadow: '0 0 5px var(--gf-neon)',
        animation: 'pulse 3s ease infinite',
        flexShrink: 0,
      }}/>
      <span style={{
        fontSize: 8, color: 'var(--gf-text-3)',
        fontFamily: 'monospace', letterSpacing: '0.12em',
        textTransform: 'uppercase',
      }}>
        {labels[mode] || 'UNKNOWN'}
      </span>
    </div>
  )
}

// ─── Coordinate HUD (bottom-left) ────────────────────────────────────────────
function CoordHUD() {
  const [pos, setPos] = useState({ x: 0, y: 0, z: 0 })
  const { camera } = useThree()

  useFrame(() => {
    const p = camera.position
    setPos({
      x: p.x.toFixed(2),
      y: p.y.toFixed(2),
      z: p.z.toFixed(2),
    })
  })

  return (
    <div style={{
      position: 'absolute', bottom: 10, left: 10, zIndex: 10,
      background: 'rgba(1,3,1,0.75)',
      border: '1px solid var(--gf-border)',
      borderRadius: 'var(--gf-radius-sm)',
      padding: '3px 8px',
      backdropFilter: 'blur(4px)',
      pointerEvents: 'none',
      fontFamily: 'monospace', fontSize: 8,
      letterSpacing: '0.08em',
    }}>
      <span style={{ color: '#FF2D55' }}>X</span>
      <span style={{ color: 'var(--gf-text-3)', margin: '0 3px' }}>{pos.x}</span>
      <span style={{ color: '#39FF14' }}>Y</span>
      <span style={{ color: 'var(--gf-text-3)', margin: '0 3px' }}>{pos.y}</span>
      <span style={{ color: '#00E5FF' }}>Z</span>
      <span style={{ color: 'var(--gf-text-3)', marginLeft: 3 }}>{pos.z}</span>
    </div>
  )
}

// ─── Scene canvas content ─────────────────────────────────────────────────────
function SceneContent({ objects, viewportGrid, orbitRef }) {
  return (
    <>
      {/* Matrix-tinted lighting setup */}
      <ambientLight intensity={0.25} color="#1A3B1A" />
      <pointLight position={[0, 6, 0]}   intensity={1.4} color="#39FF14" distance={25} />
      <pointLight position={[5, 3, 5]}   intensity={0.6} color="#00E5FF" distance={18} />
      <pointLight position={[-5, -2, -5]} intensity={0.3} color="#39FF14" distance={12} />

      {/* Neon green grid */}
      {viewportGrid && <MatrixGrid />}

      {/* Axis helpers */}
      <NeonAxes />

      {/* Scene objects */}
      <Suspense fallback={null}>
        {objects.map(obj => <SceneObject key={obj.id} obj={obj} />)}
      </Suspense>

      {/* Camera controls */}
      <Controls orbitRef={orbitRef} />

      {/* Coord display */}
      <CoordHUD />
    </>
  )
}

// ─── Main Viewport ────────────────────────────────────────────────────────────
export default function Viewport() {
  const { objects, activeJob, viewportMode } = useSceneStore()
  const { viewportGrid } = useSettingsStore()
  const orbitRef = useRef()
  const isEmpty  = objects.length === 0

  return (
    <div style={{
      flex: 1, position: 'relative', overflow: 'hidden',
      background: '#010301',
    }}>
      {/* Matrix rain — subtle, atmospheric */}
      <MatrixRain opacity={0.05} fontSize={12} speed={0.65} />

      {/* View mode HUD — top left */}
      <ViewportHUD mode={viewportMode} />

      {/* Three.js canvas */}
      <Canvas
        style={{
          position: 'absolute', inset: 0,
          width: '100%', height: '100%', zIndex: 1,
        }}
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
          orbitRef={orbitRef}
        />

        {/* Camera presets inside Canvas so useThree works */}
        <CameraPresets orbitRef={orbitRef} />
      </Canvas>

      {/* Empty overlay — above canvas */}
      <EmptySceneOverlay show={isEmpty} />

      {/* Job progress HUD */}
      <JobHUD job={activeJob} />

      {/* CRT vignette — edge darkening */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none',
        background: 'radial-gradient(ellipse at center, transparent 45%, rgba(1,3,1,0.65) 100%)',
      }}/>

      {/* Corner bracket decorations — Matrix aesthetic */}
      {[
        { top: 8, left: 8 },
        { top: 8, right: 8 },
        { bottom: 8, left: 8 },
        { bottom: 8, right: 8 },
      ].map((pos, i) => (
        <svg key={i} width="14" height="14" viewBox="0 0 14 14" fill="none"
             style={{
               position: 'absolute', zIndex: 3, pointerEvents: 'none',
               opacity: 0.35,
               transform: `rotate(${i * 90}deg)`,
               ...pos,
             }}>
          <path d="M1 8 L1 1 L8 1" stroke="#39FF14" strokeWidth="1.2" fill="none"/>
        </svg>
      ))}
    </div>
  )
}
