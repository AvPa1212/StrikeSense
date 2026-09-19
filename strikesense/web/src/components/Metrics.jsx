import { Lock } from 'lucide-react'
import { fmt, scoreColor } from '../lib/format.js'

const DIGITS = { contact_lat: 2, contact_vert: 2, speed_ms: 1, contact_ms: 1 }

function Track({ m }) {
  // Scale runs from three bands below the benchmark to three bands above it.
  const lo = m.target - 3 * m.band
  const span = 6 * m.band
  const pos = (v) => Math.max(0, Math.min(100, ((v - lo) / span) * 100))
  const bandL = pos(m.target - m.band)
  const bandR = pos(m.target + m.band)
  return (
    <div className="relative h-7" aria-hidden="true">
      <div className="absolute left-0 right-0 top-[13px] h-[3px] rounded bg-chalk/15" />
      <div className="absolute top-[9px] h-[11px] rounded-sm bg-grass/30" style={{ left: `${bandL}%`, width: `${bandR - bandL}%` }} />
      <div className="absolute top-[3px] h-[23px] w-px bg-chalk/50" style={{ left: `${pos(m.target)}%` }} />
      <div
        className="absolute top-[2px] h-6 w-[6px] -translate-x-1/2 rounded-sm"
        style={{ left: `${pos(m.value)}%`, background: scoreColor(m.score), transition: 'left 600ms cubic-bezier(.2,.8,.2,1)' }}
      />
    </div>
  )
}

export default function Metrics({ kick }) {
  const rows = kick ? [...kick.score.metrics].sort((a, b) => b.weight - a.weight) : []
  return (
    <section className="field p-5" aria-label="Kick metrics against benchmark">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-2xl font-semibold">Against the benchmark</h2>
        <p className="chalk-text text-sm">Ordered by how much each stat counts. The green band is the target range.</p>
      </div>
      {!kick && <p className="chalk-text mt-3">Metrics fill in after a kick.</p>}
      <ul className="mt-2 divide-y rule">
        {rows.map((m) => (
          <li key={m.key} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 py-2.5 sm:grid-cols-[minmax(130px,1.1fr)_minmax(140px,2.2fr)_minmax(96px,0.8fr)] rule">
            <div>
              <p className="font-medium leading-tight">{m.label}</p>
              <p className="chalk-text text-xs">
                Counts for {Math.round(m.weight * 100)}%
                {m.target !== null && m.available ? `, target ${fmt(m.target, DIGITS[m.key] ?? 0)} ${m.unit}` : ''}
              </p>
            </div>
            <div className="order-last col-span-2 sm:order-none sm:col-span-1">
              {m.available ? (
                <Track m={m} />
              ) : (
                <div className="flex items-center gap-2 rounded border border-dashed border-chalk/35 px-3 py-1.5 text-xs text-chalk/70">
                  <Lock size={14} aria-hidden="true" />
                  {m.reason}
                </div>
              )}
            </div>
            <div className="text-right">
              <p className="font-display text-3xl font-semibold leading-none">
                {m.available ? fmt(m.value, DIGITS[m.key] ?? 0) : 'n/a'}
                <span className="chalk-text ml-1 font-sans text-xs font-normal">{m.available ? m.unit : ''}</span>
              </p>
              <p className="text-xs font-semibold" style={{ color: scoreColor(m.score) }}>
                {m.available ? `${Math.round(m.score)} of 100` : ' '}
              </p>
            </div>
          </li>
        ))}
      </ul>
      {kick && kick.score.coverage < 1 && (
        <p className="chalk-text mt-2 text-sm">
          The score uses the {Math.round(kick.score.coverage * 100)}% of stats this sensor can measure.
        </p>
      )}
    </section>
  )
}
