import { useEffect, useRef } from 'react'

const WINDOW = 2000 // 4 seconds at 500 Hz
const LANES = [
  { name: 'Acceleration (g)', color: '#f2f5ec', min: 6, get: (s) => Math.hypot(s.a[0], s.a[1], s.a[2]) },
  { name: 'Spin (deg/s)', color: '#ffd23f', min: 300, get: (s) => Math.hypot(s.g[0], s.g[1], s.g[2]) },
]
const FORCE_COLORS = ['#ff6b1a', '#8fe08a', '#ffd23f', '#f2f5ec']

export default function LiveTrace({ live }) {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas.getContext('2d')
    let raf
    const draw = () => {
      const dpr = window.devicePixelRatio || 1
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr
        canvas.height = h * dpr
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      const buf = live.current
      const n = Math.min(buf.length, WINDOW)
      const start = buf.length - n
      const laneH = (h - 8) / 3
      const cols = Math.floor(w)
      const per = Math.max(1, WINDOW / cols)

      const columnMax = (fn) => {
        const out = new Float32Array(cols)
        for (let i = 0; i < n; i++) {
          const x = Math.min(cols - 1, Math.floor(((WINDOW - n + i) / WINDOW) * cols))
          const v = fn(buf[start + i])
          if (v > out[x]) out[x] = v
        }
        return out
      }

      for (let li = 0; li < 3; li++) {
        const top = 4 + li * laneH
        ctx.strokeStyle = 'rgba(242,245,236,0.14)'
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(0, top + laneH - 0.5)
        ctx.lineTo(w, top + laneH - 0.5)
        ctx.stroke()
        ctx.fillStyle = 'rgba(242,245,236,0.62)'
        ctx.font = '12px Barlow, sans-serif'
        ctx.fillText(li < 2 ? LANES[li].name : 'Force sensors (A0 to A3)', 6, top + 14)

        const line = (series, max, color) => {
          ctx.strokeStyle = color
          ctx.lineWidth = 1.6
          ctx.beginPath()
          for (let x = 0; x < cols; x++) {
            const y = top + laneH - 3 - (Math.min(series[x], max) / max) * (laneH - 22)
            if (x === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          }
          ctx.stroke()
        }

        if (li < 2) {
          const s = columnMax(LANES[li].get)
          let max = LANES[li].min
          for (let x = 0; x < cols; x++) if (s[x] * 1.1 > max) max = s[x] * 1.1
          line(s, max, LANES[li].color)
          ctx.fillStyle = 'rgba(242,245,236,0.5)'
          ctx.textAlign = 'right'
          ctx.fillText(String(Math.round(max)), w - 6, top + 14)
          ctx.textAlign = 'left'
        } else {
          for (let c = 0; c < 4; c++) line(columnMax((s) => s.f[c]), 1023, FORCE_COLORS[c])
        }
      }
      void per
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [live])

  return (
    <section className="field p-5" aria-label="Live sensor trace">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-2xl font-semibold">Live trace</h2>
        <p className="chalk-text text-sm">Last 4 seconds, peaks kept</p>
      </div>
      <canvas ref={ref} className="mt-2 block h-[270px] w-full" role="img"
        aria-label="Live acceleration, spin and force traces" />
    </section>
  )
}
