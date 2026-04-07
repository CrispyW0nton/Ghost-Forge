import React, { useEffect, useRef } from 'react'

/* ── Matrix Digital Rain ───────────────────────────────────────────────────────
   Authentic Matrix code rain — katakana + latin + hex, glowing neon green
   Multiple stream speeds, head glow, variable brightness
*/

// Full katakana half-width + digits + hex chars + symbols
const CHARS = 'ｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789ABCDEF><=-+*/\\|!?@#$%^&'

export default function MatrixRain({ opacity = 0.08, fontSize = 13, speed = 1.0 }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    let animId
    let cols
    let streams = []
    let lastTime = 0

    function randChar() {
      return CHARS[Math.floor(Math.random() * CHARS.length)]
    }

    function init() {
      canvas.width  = canvas.offsetWidth  || 800
      canvas.height = canvas.offsetHeight || 600
      cols = Math.floor(canvas.width / fontSize)

      streams = []
      for (let i = 0; i < cols; i++) {
        streams.push({
          x:      i * fontSize,
          y:      Math.random() * -canvas.height * 1.5,
          speed:  0.3 + Math.random() * 0.9,     // each column different speed
          length: 8 + Math.floor(Math.random() * 20),  // trail length
          chars:  [],
          mutTimer: 0,
        })
        // Fill with random chars
        for (let j = 0; j < 30; j++) {
          streams[i].chars.push(randChar())
        }
      }
    }

    function draw(timestamp) {
      const dt = timestamp - lastTime
      const interval = 28 / speed
      if (dt < interval) { animId = requestAnimationFrame(draw); return }
      lastTime = timestamp

      // Dark fade — preserve long trails
      ctx.fillStyle = 'rgba(1, 3, 1, 0.055)'
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      ctx.font = `${fontSize}px monospace`

      for (const s of streams) {
        s.y += s.speed

        // Randomly mutate characters in stream
        s.mutTimer++
        if (s.mutTimer > 3) {
          s.mutTimer = 0
          const idx = Math.floor(Math.random() * s.chars.length)
          s.chars[idx] = randChar()
        }

        for (let j = 0; j < s.length; j++) {
          const cy = s.y - j * fontSize
          if (cy < 0 || cy > canvas.height) continue

          const char = s.chars[j % s.chars.length]

          if (j === 0) {
            // HEAD — white/bright green with strong glow
            ctx.shadowColor  = '#39FF14'
            ctx.shadowBlur   = 12
            ctx.fillStyle    = '#E0FFE0'
          } else if (j === 1) {
            // NECK — bright neon
            ctx.shadowColor  = '#39FF14'
            ctx.shadowBlur   = 7
            ctx.fillStyle    = '#39FF14'
          } else if (j < 4) {
            // UPPER BODY — neon
            ctx.shadowColor  = '#39FF14'
            ctx.shadowBlur   = 4
            ctx.fillStyle    = '#28CC10'
          } else if (j < 8) {
            // MID BODY — dim neon
            ctx.shadowBlur   = 2
            ctx.fillStyle    = '#149A08'
          } else {
            // TAIL — dark, fading
            const fade = 1 - (j - 8) / Math.max(1, s.length - 8)
            ctx.shadowBlur   = 0
            const g = Math.floor(fade * 80)
            ctx.fillStyle    = `rgb(0, ${g}, 0)`
          }

          ctx.fillText(char, s.x, cy)
        }

        ctx.shadowBlur = 0

        // Reset when stream completely past bottom
        if (s.y - s.length * fontSize > canvas.height) {
          s.y = Math.random() * -canvas.height * 0.5
          s.speed  = 0.3 + Math.random() * 0.9
          s.length = 8 + Math.floor(Math.random() * 20)
        }
      }

      animId = requestAnimationFrame(draw)
    }

    init()
    animId = requestAnimationFrame(draw)

    const observer = new ResizeObserver(() => {
      init()
    })
    observer.observe(canvas)

    return () => {
      cancelAnimationFrame(animId)
      observer.disconnect()
    }
  }, [fontSize, speed])

  return (
    <canvas
      ref={canvasRef}
      className="matrix-rain-canvas"
      style={{ opacity, width: '100%', height: '100%' }}
    />
  )
}
