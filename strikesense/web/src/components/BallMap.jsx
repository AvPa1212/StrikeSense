import { fmt, spinWords } from '../lib/format.js'

const CX = 170
const CY = 170
const R = 120

// Force sensor positions from the kicker's view (looking along +X, +Y is screen left).
// Sensors with x < 0 sit on the face toward the kicker; the others are behind the ball.
const S3 = Math.sqrt(3)
const SENSORS = [
  { pin: 'A0', p: [1, 1, 1] },
  { pin: 'A1', p: [1, -1, -1] },
  { pin: 'A2', p: [-1, 1, -1] },
  { pin: 'A3', p: [-1, -1, 1] },
].map((s) => ({
  pin: s.pin,
  front: s.p[0] < 0,
  x: CX - (s.p[1] / S3) * R * 0.86,
  y: CY - (s.p[2] / S3) * R * 0.86,
}))

function pentagon(cx, cy, r) {
  const pts = []
  for (let i = 0; i < 5; i++) {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / 5
    pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)])
  }
  return pts
}

export default function BallMap({ kick, bench, pulse }) {
  const f = kick?.features
  const hasContact = f && f.contact_lat !== null && f.contact_lat !== undefined
  const cx = hasContact ? CX - f.contact_lat * R : null
  const cy = hasContact ? CY - f.contact_vert * R : null
  const bl = bench?.contact_lat
  const bv = bench?.contact_vert
  const pent = pentagon(CX, CY, 34)
  const side = f?.sidespin_dps ?? 0
  const arcDir = side >= 0 ? -1 : 1 // curls left points the arrow left
  const thick = 2 + Math.min(4, Math.abs(side) / 500)

  return (
    <section className="boxed p-5" aria-label="Strike map">
      <h2 className="font-display text-2xl font-semibold">Strike map</h2>
      <p className="chalk-text text-sm">Ball seen from where you stand.</p>
      <svg viewBox="0 0 340 360" className="mx-auto mt-2 block w-full max-w-[380px]" role="img"
        aria-label={hasContact ? `Contact ${fmt(f.contact_lat, 2)} sideways, ${fmt(f.contact_vert, 2)} up` : 'No strike point yet'}>
        <defs>
          <marker id="arrowhead" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill="#ffd23f" />
          </marker>
        </defs>

        <circle cx={CX} cy={CY} r={R} fill="#f2f5ec" fillOpacity="0.05" stroke="#f2f5ec" strokeWidth="3" />
        <polygon points={pent.map((p) => p.join(',')).join(' ')} fill="none" stroke="#f2f5ec" strokeOpacity="0.28" strokeWidth="2" />
        {pent.map(([x, y], i) => {
          const a = Math.atan2(y - CY, x - CX)
          return <line key={i} x1={x} y1={y} x2={CX + Math.cos(a) * (R - 6)} y2={CY + Math.sin(a) * (R - 6)}
            stroke="#f2f5ec" strokeOpacity="0.2" strokeWidth="2" />
        })}
        <line x1={CX - R} y1={CY} x2={CX + R} y2={CY} stroke="#f2f5ec" strokeOpacity="0.18" strokeDasharray="4 6" />
        <line x1={CX} y1={CY - R} x2={CX} y2={CY + R} stroke="#f2f5ec" strokeOpacity="0.18" strokeDasharray="4 6" />

        {bench && bl !== undefined && (
          <ellipse cx={CX - bl.mu * R} cy={CY - bv.mu * R} rx={Math.max(10, bl.sd * R)} ry={Math.max(10, bv.sd * R)}
            fill="#8fe08a" fillOpacity="0.14" stroke="#8fe08a" strokeWidth="2" strokeDasharray="5 4" />
        )}

        {SENSORS.map((s) => (
          <g key={s.pin}>
            <rect x={s.x - 9} y={s.y - 9} width="18" height="18" rx="3"
              fill={s.front ? '#0b3020' : 'none'} stroke="#f2f5ec" strokeWidth="2"
              strokeDasharray={s.front ? undefined : '3 3'} strokeOpacity={s.front ? 1 : 0.55} />
            <text x={s.x} y={s.y + 4} textAnchor="middle" fontSize="10" fontWeight="600" fill="#f2f5ec"
              fillOpacity={s.front ? 1 : 0.55}>{s.pin}</text>
          </g>
        ))}

        {f && (
          <>
            <path d={`M ${CX + arcDir * -70} ${CY - R - 16} Q ${CX} ${CY - R - 46} ${CX + arcDir * 70} ${CY - R - 16}`}
              fill="none" stroke="#ffd23f" strokeWidth={thick} strokeLinecap="round" markerEnd="url(#arrowhead)"
              opacity={Math.abs(side) < 150 ? 0.25 : 1} />
            {hasContact && (
              <>
                <g key={pulse}>
                  <circle className="strike-ring" cx={cx} cy={cy} r="14" fill="none" stroke="#ff6b1a" strokeWidth="3" />
                </g>
                <circle cx={cx} cy={cy} r="9" fill="#ff6b1a" stroke="#f2f5ec" strokeWidth="2.5" />
              </>
            )}
          </>
        )}
        {!hasContact && (
          <text x={CX} y={CY + 4} textAnchor="middle" fontSize="14" fill="#f2f5ec" fillOpacity="0.55">
            {f ? 'No force sensor reading' : 'Contact point appears here'}
          </text>
        )}
        <text x={CX} y={CY + R + 30} textAnchor="middle" fontSize="13" fill="#f2f5ec" fillOpacity="0.8">
          {f ? `Sidespin ${fmt(Math.abs(side))} deg/s, ${spinWords(side)}` : ' '}
        </text>
        <text x={CX} y={CY + R + 50} textAnchor="middle" fontSize="13" fill="#f2f5ec" fillOpacity="0.8">
          {f ? `${f.topspin_dps >= 0 ? 'Topspin' : 'Backspin'} ${fmt(Math.abs(f.topspin_dps))} deg/s` : ' '}
        </text>
      </svg>
      <ul className="chalk-text mt-1 flex flex-wrap justify-center gap-x-5 gap-y-1 text-xs">
        <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-full bg-cone" />Where the foot met the ball</li>
        <li className="flex items-center gap-2"><span className="inline-block h-3 w-4 rounded-sm border-2 border-dashed border-grass" />Benchmark zone</li>
        <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm border-2 border-chalk" />Force sensor</li>
      </ul>
      {f && (
        <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-chalk/25 pt-3 text-center">
          <div>
            <dt className="chalk-text text-xs">Airborne</dt>
            <dd className="font-display text-2xl font-semibold">{fmt(f.hang_ms / 1000, 2)} s</dd>
          </div>
          <div>
            <dt className="chalk-text text-xs">Apex height</dt>
            <dd className="font-display text-2xl font-semibold">{fmt(f.apex_m, 1)} m</dd>
          </div>
          <div>
            <dt className="chalk-text text-xs">Contact</dt>
            <dd className="font-display text-2xl font-semibold">{fmt(f.contact_ms, 1)} ms</dd>
          </div>
        </dl>
      )}
    </section>
  )
}
