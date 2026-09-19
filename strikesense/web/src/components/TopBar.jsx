import { useState } from 'react'
import { Activity, Cable, Goal, RotateCcw, Zap } from 'lucide-react'

const TARGETS = [
  ['auto', 'Auto'],
  ['drive', 'Drive'],
  ['curl', 'Curl'],
  ['chip', 'Chip'],
  ['pass', 'Pass'],
  ['knuckle', 'Knuckle'],
]

function Ball() {
  return (
    <svg viewBox="0 0 32 32" className="h-9 w-9" aria-hidden="true">
      <circle cx="16" cy="16" r="14" fill="#0b3020" stroke="#f2f5ec" strokeWidth="2" />
      <path d="M16 9l6 4.5-2.3 7h-7.4L10 13.5z" fill="#ff6b1a" />
      <path d="M16 9V4M22 13.5l5-2M19.7 20.5l3 4.5M12.3 20.5l-3 4.5M10 13.5l-5-2" stroke="#f2f5ec" strokeWidth="1.4" />
    </svg>
  )
}

export default function TopBar({ page, setPage, status, connected, setTarget, simulate, newSession }) {
  const [tech, setTech] = useState('')
  const [level, setLevel] = useState('good')
  const [busy, setBusy] = useState(false)
  const isSim = status?.source === 'simulator'
  const live = connected && status && status.rate_hz > 0

  const run = async () => {
    setBusy(true)
    try {
      await simulate(tech || null, level)
    } finally {
      setTimeout(() => setBusy(false), 700)
    }
  }

  const tabs = [
    ['pitch', 'Pitch', Goal],
    ['sensors', 'Sensors', Activity],
  ]

  return (
    <header className="border-b-2 border-chalk/80 bg-turf-950/70 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-8 gap-y-3 px-5 py-3">
        <div className="flex items-center gap-3">
          <Ball />
          <h1 className="font-display text-[2rem] font-extrabold leading-none tracking-tight">StrikeSense</h1>
        </div>

        <nav className="flex gap-1" aria-label="Pages">
          {tabs.map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => setPage(key)}
              aria-current={page === key ? 'page' : undefined}
              className={`flex items-center gap-2 border-b-[3px] px-3 py-2 text-[15px] font-semibold transition-colors ${
                page === key ? 'border-cone text-chalk' : 'border-transparent text-chalk/60 hover:text-chalk'
              }`}
            >
              <Icon size={17} aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3 text-sm">
          <span
            className={`h-2.5 w-2.5 rounded-full ${live ? 'bg-grass' : 'bg-flag'}`}
            role="img"
            aria-label={live ? 'Receiving data' : 'No data'}
          />
          <span className="chalk-text">
            {!connected
              ? 'Server offline. Start it with uvicorn app:app'
              : status
                ? `${isSim ? 'Simulator' : 'Arduino'}, ${status.rate_hz} Hz, accel ±${status.accel_range_g} g`
                : 'Connecting'}
          </span>
          {status && !isSim && <Cable size={16} className="text-chalk/60" aria-hidden="true" />}
        </div>
      </div>

      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-6 gap-y-2 px-5 pb-3">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Technique you are practising">
          <span className="chalk-text mr-1 text-sm">Practising</span>
          {TARGETS.map(([key, label]) => {
            const on = (status?.target || 'auto') === key
            return (
              <button
                key={key}
                onClick={() => setTarget(key)}
                aria-pressed={on}
                className={`rounded-full border px-3.5 py-1 text-sm font-medium transition-colors ${
                  on
                    ? 'border-card bg-card text-turf-950'
                    : 'border-chalk/40 text-chalk/85 hover:border-chalk hover:text-chalk'
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2 text-sm">
          {isSim && (
            <>
              <label className="sr-only" htmlFor="sim-tech">Simulated technique</label>
              <select
                id="sim-tech"
                value={tech}
                onChange={(e) => setTech(e.target.value)}
                className="rounded-md border border-chalk/40 bg-turf-950 px-2 py-1.5"
              >
                <option value="">Any technique</option>
                {TARGETS.slice(1).map(([k, l]) => (
                  <option key={k} value={k}>{l}</option>
                ))}
              </select>
              <label className="sr-only" htmlFor="sim-level">Simulated skill level</label>
              <select
                id="sim-level"
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                className="rounded-md border border-chalk/40 bg-turf-950 px-2 py-1.5"
              >
                <option value="pro">Pro</option>
                <option value="good">Good</option>
                <option value="amateur">Amateur</option>
              </select>
              <button
                onClick={run}
                disabled={busy}
                className="flex items-center gap-2 rounded-md bg-cone px-4 py-1.5 font-semibold text-turf-950 transition-opacity hover:opacity-90 disabled:opacity-60"
              >
                <Zap size={16} aria-hidden="true" />
                Simulate kick
              </button>
            </>
          )}
          <button
            onClick={newSession}
            className="flex items-center gap-2 rounded-md border border-chalk/40 px-3 py-1.5 text-chalk/85 hover:border-chalk hover:text-chalk"
          >
            <RotateCcw size={15} aria-hidden="true" />
            New session
          </button>
        </div>
      </div>
    </header>
  )
}
