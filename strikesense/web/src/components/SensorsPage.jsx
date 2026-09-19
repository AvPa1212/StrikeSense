import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Crosshair, Download } from 'lucide-react'
import { api } from '../lib/useStrikeSense.js'
import { TECH_LABEL, fmt, timeOf } from '../lib/format.js'

const SENSORS = [
  { key: 'ax', label: 'Accelerometer X', unit: 'g', get: (r) => r.a[0], d: 2, span: 2 },
  { key: 'ay', label: 'Accelerometer Y', unit: 'g', get: (r) => r.a[1], d: 2, span: 2 },
  { key: 'az', label: 'Accelerometer Z', unit: 'g', get: (r) => r.a[2], d: 2, span: 2 },
  { key: 'gx', label: 'Gyroscope X (roll)', unit: 'deg/s', get: (r) => r.g[0], d: 0, span: 100 },
  { key: 'gy', label: 'Gyroscope Y (top/back)', unit: 'deg/s', get: (r) => r.g[1], d: 0, span: 100 },
  { key: 'gz', label: 'Gyroscope Z (side)', unit: 'deg/s', get: (r) => r.g[2], d: 0, span: 100 },
  { key: 'f0', label: 'Force A0', unit: 'counts', get: (r) => r.f[0], d: 0, span: 100 },
  { key: 'f1', label: 'Force A1', unit: 'counts', get: (r) => r.f[1], d: 0, span: 100 },
  { key: 'f2', label: 'Force A2', unit: 'counts', get: (r) => r.f[2], d: 0, span: 100 },
  { key: 'f3', label: 'Force A3', unit: 'counts', get: (r) => r.f[3], d: 0, span: 100 },
]
const PAGE = 100

function toRows(w) {
  return w.t.map((t, i) => ({ t, a: w.a[i], g: w.g[i], f: w.f[i] }))
}

function Spark({ rows, get, shade, minSpan = 0 }) {
  const W = 260
  const H = 54
  const step = Math.max(1, Math.ceil(rows.length / W))
  const vals = []
  for (let i = 0; i < rows.length; i += step) {
    let best = get(rows[i])
    for (let j = i; j < Math.min(rows.length, i + step); j++) {
      const v = get(rows[j])
      if (Math.abs(v) > Math.abs(best)) best = v
    }
    vals.push(best)
  }
  if (vals.length < 2) return <div className="h-[54px]" />
  let lo = Math.min(...vals)
  let hi = Math.max(...vals)
  if (hi - lo < minSpan) {
    const mid = (hi + lo) / 2
    lo = mid - minSpan / 2
    hi = mid + minSpan / 2
  }
  const span = hi - lo || 1
  const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * W},${H - 4 - ((v - lo) / span) * (H - 8)}`).join(' ')
  const t0 = rows[0].t
  const tN = rows[rows.length - 1].t
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-[54px] w-full" preserveAspectRatio="none" aria-hidden="true">
      {shade && tN > t0 && (
        <rect x={((shade[0] - t0) / (tN - t0)) * W} width={Math.max(2, ((shade[1] - shade[0]) / (tN - t0)) * W)}
          y="0" height={H} fill="#ff6b1a" fillOpacity="0.28" />
      )}
      <polyline points={pts} fill="none" stroke="#f2f5ec" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export default function SensorsPage({ live, kicks, selectedId }) {
  const [mode, setMode] = useState('live') // 'live' or a kick id
  const [win, setWin] = useState(null)
  const [tick, setTick] = useState(0)
  const [page, setPage] = useState(0)

  useEffect(() => {
    if (mode !== 'live') return
    const id = setInterval(() => setTick((t) => t + 1), 200)
    return () => clearInterval(id)
  }, [mode])

  useEffect(() => {
    if (mode === 'live') {
      setWin(null)
      return
    }
    let alive = true
    api(`/api/kicks/${mode}`).then((k) => alive && setWin(k)).catch(() => {})
    return () => { alive = false }
  }, [mode])

  const kickRows = useMemo(() => (win ? toRows(win.window) : null), [win])
  const rows = mode === 'live' ? live.current.slice(-1000) : kickRows || []
  const contact = win?.features?.t_contact
  const shade = contact ? [contact[0] + (kickRows?.[0]?.t ?? 0), contact[1] + (kickRows?.[0]?.t ?? 0)] : null
  const last = rows[rows.length - 1]
  void tick

  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const p = Math.min(page, pages - 1)
  const slice = mode === 'live' ? rows.slice(-PAGE).reverse() : rows.slice(p * PAGE, p * PAGE + PAGE)

  const jumpToContact = () => {
    if (!shade || !rows.length) return
    const i = rows.findIndex((r) => r.t >= shade[0])
    setPage(Math.max(0, Math.floor((i - 10) / PAGE)))
  }

  const download = () => {
    const src = mode === 'live' ? live.current.slice(-3000) : rows
    const head = 't_s,ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,f0,f1,f2,f3\n'
    const body = src.map((r) => [r.t, ...r.a, ...r.g, ...r.f].join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([head + body], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = mode === 'live' ? 'strikesense-live.csv' : `strikesense-kick-${mode}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const inContact = (r) => shade && r.t >= shade[0] && r.t <= shade[1]

  return (
    <div className="space-y-5">
      <section className="field flex flex-wrap items-center gap-3 p-5" aria-label="Data source">
        <h2 className="mr-2 font-display text-2xl font-semibold">Raw sensors</h2>
        <label htmlFor="src" className="chalk-text text-sm">Showing</label>
        <select id="src" value={mode} onChange={(e) => { setMode(e.target.value === 'live' ? 'live' : Number(e.target.value)); setPage(0) }}
          className="rounded-md border border-chalk/40 bg-turf-950 px-2 py-1.5 text-sm">
          <option value="live">Live stream, last 2 seconds</option>
          {[...kicks].reverse().map((k, i) => (
            <option key={k.id} value={k.id}>
              Kick {kicks.length - i}: {TECH_LABEL[k.technique]} at {timeOf(k.ts)}{k.id === selectedId ? ' (selected)' : ''}
            </option>
          ))}
        </select>
        <button onClick={download}
          className="ml-auto flex items-center gap-2 rounded-md border border-chalk/40 px-3 py-1.5 text-sm hover:border-chalk">
          <Download size={15} aria-hidden="true" />
          Download CSV
        </button>
      </section>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {SENSORS.map((s) => {
          const vals = rows.map(s.get)
          const lo = vals.length ? Math.min(...vals) : null
          const hi = vals.length ? Math.max(...vals) : null
          return (
            <article key={s.key} className="field p-4" aria-label={s.label}>
              <h3 className="text-sm font-semibold leading-tight">{s.label}</h3>
              <p className="mt-1 font-mono text-2xl font-medium">
                {last ? fmt(s.get(last), s.d) : 'n/a'}
                <span className="chalk-text ml-1 font-sans text-xs">{s.unit}</span>
              </p>
              <Spark rows={rows} get={s.get} shade={mode === 'live' ? null : shade} minSpan={s.span} />
              <p className="chalk-text font-mono text-xs">
                {lo !== null ? `${fmt(lo, s.d)} to ${fmt(hi, s.d)}` : 'No data yet'}
              </p>
            </article>
          )
        })}
      </div>

      <section className="field p-5" aria-label="Raw samples table">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-display text-2xl font-semibold">Samples</h2>
          {mode !== 'live' && (
            <>
              <span className="chalk-text text-sm">
                Rows {rows.length ? p * PAGE + 1 : 0} to {Math.min(rows.length, (p + 1) * PAGE)} of {rows.length}
              </span>
              <div className="ml-auto flex items-center gap-2">
                <button onClick={jumpToContact} className="flex items-center gap-2 rounded-md border border-chalk/40 px-3 py-1 text-sm hover:border-chalk">
                  <Crosshair size={14} aria-hidden="true" />
                  Jump to contact
                </button>
                <button onClick={() => setPage(Math.max(0, p - 1))} disabled={p === 0} aria-label="Previous rows"
                  className="rounded-md border border-chalk/40 p-1.5 hover:border-chalk disabled:opacity-40"><ChevronLeft size={16} /></button>
                <button onClick={() => setPage(Math.min(pages - 1, p + 1))} disabled={p >= pages - 1} aria-label="Next rows"
                  className="rounded-md border border-chalk/40 p-1.5 hover:border-chalk disabled:opacity-40"><ChevronRight size={16} /></button>
              </div>
            </>
          )}
          {mode === 'live' && <span className="chalk-text text-sm">Newest first, refreshes five times a second</span>}
        </div>
        <div className="mt-3 max-h-[420px] overflow-auto rounded border border-chalk/20">
          <table className="w-full min-w-[820px] border-collapse font-mono text-[13px]">
            <thead className="sticky top-0 bg-turf-950 text-left">
              <tr>
                {['t (s)', 'ax', 'ay', 'az', 'gx', 'gy', 'gz', 'A0', 'A1', 'A2', 'A3'].map((h) => (
                  <th key={h} scope="col" className="px-3 py-2 font-medium text-chalk/70">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {slice.length === 0 && (
                <tr><td colSpan="11" className="px-3 py-6 font-sans text-chalk/60">No samples yet. Check the connection.</td></tr>
              )}
              {slice.map((r, i) => (
                <tr key={i} className={`border-t border-chalk/10 ${inContact(r) ? 'bg-cone/25' : ''}`}>
                  <td className="px-3 py-1">{r.t.toFixed(3)}</td>
                  {r.a.map((v, j) => <td key={'a' + j} className="px-3 py-1">{v.toFixed(2)}</td>)}
                  {r.g.map((v, j) => <td key={'g' + j} className="px-3 py-1">{v.toFixed(0)}</td>)}
                  {r.f.map((v, j) => <td key={'f' + j} className="px-3 py-1">{v}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {mode !== 'live' && shade && <p className="chalk-text mt-2 text-xs">Orange rows mark foot contact.</p>}
      </section>
    </div>
  )
}
