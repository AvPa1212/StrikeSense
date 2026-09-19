import { useState } from 'react'
import { BrainCircuit, Tag } from 'lucide-react'
import { TECH_LABEL, fmt, scoreColor, timeOf } from '../lib/format.js'

function Trend({ kicks, selectedId, onSelect }) {
  const W = 620
  const H = 150
  const pad = 22
  const pts = kicks.map((k, i) => ({
    k,
    x: kicks.length === 1 ? W / 2 : pad + (i / (kicks.length - 1)) * (W - pad * 2),
    y: H - pad - (k.overall / 100) * (H - pad * 2),
  }))
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label="Score for each kick this session">
      {[0, 50, 100].map((v) => {
        const y = H - pad - (v / 100) * (H - pad * 2)
        return (
          <g key={v}>
            <line x1={pad} x2={W - pad} y1={y} y2={y} stroke="#f2f5ec" strokeOpacity="0.14" />
            <text x={0} y={y + 4} fontSize="11" fill="#f2f5ec" fillOpacity="0.55">{v}</text>
          </g>
        )
      })}
      {pts.length > 1 && (
        <polyline points={pts.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="#f2f5ec" strokeOpacity="0.55" strokeWidth="2" />
      )}
      {pts.map((p) => (
        <circle key={p.k.id} cx={p.x} cy={p.y} r={p.k.id === selectedId ? 8 : 5.5} fill={scoreColor(p.k.overall)}
          stroke={p.k.id === selectedId ? '#f2f5ec' : 'none'} strokeWidth="2.5" className="cursor-pointer"
          onClick={() => onSelect(p.k.id)}>
          <title>{`Kick: ${TECH_LABEL[p.k.technique]}, ${Math.round(p.k.overall)}`}</title>
        </circle>
      ))}
    </svg>
  )
}

export default function Session({ kicks, selected, selectKick, labelKick, retrain, status }) {
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const doRetrain = async () => {
    setBusy(true)
    setMsg('')
    try {
      const r = await retrain()
      setMsg(`Retrained with ${r.real_kicks} real kick${r.real_kicks === 1 ? '' : 's'}. Held-out accuracy ${fmt(r.holdout_accuracy * 100)}%.`)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="field p-5" aria-label="Session">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-2xl font-semibold">Session</h2>
        <p className="chalk-text text-sm">{kicks.length} kick{kicks.length === 1 ? '' : 's'}</p>
      </div>

      {kicks.length === 0 ? (
        <p className="chalk-text mt-3">Your kicks line up here so you can see if you are improving.</p>
      ) : (
        <>
          <div className="mt-2"><Trend kicks={kicks} selectedId={selected?.id} onSelect={selectKick} /></div>
          <ul className="mt-2 max-h-[220px] divide-y overflow-y-auto rule pr-1">
            {[...kicks].reverse().map((k, i) => (
              <li key={k.id} className="rule">
                <button
                  onClick={() => selectKick(k.id)}
                  aria-current={k.id === selected?.id}
                  className={`grid w-full grid-cols-[2.5rem_1fr_auto_auto] items-center gap-3 px-2 py-2 text-left text-sm transition-colors hover:bg-chalk/10 ${
                    k.id === selected?.id ? 'bg-chalk/10' : ''
                  }`}
                >
                  <span className="chalk-text">{kicks.length - i}</span>
                  <span>
                    {TECH_LABEL[k.technique]}
                    {k.label && <span className="ml-2 rounded bg-grass/25 px-1.5 py-0.5 text-xs">labeled {k.label}</span>}
                  </span>
                  <span className="chalk-text">{timeOf(k.ts)}</span>
                  <span className="w-9 text-right font-display text-xl font-semibold" style={{ color: scoreColor(k.overall) }}>
                    {Math.round(k.overall)}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {selected && (
            <div className="mt-4 border-t border-chalk/25 pt-3">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <Tag size={15} aria-hidden="true" />
                What did you actually hit? Teach the network with this kick.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(TECH_LABEL).map(([k, l]) => (
                  <button key={k} onClick={() => labelKick(selected.id, selected.label === k ? null : k)}
                    aria-pressed={selected.label === k}
                    className={`rounded-full border px-3 py-1 text-sm ${selected.label === k ? 'border-grass bg-grass text-turf-950' : 'border-chalk/40 hover:border-chalk'}`}>
                    {l}
                  </button>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button onClick={doRetrain} disabled={busy}
                  className="flex items-center gap-2 rounded-md bg-card px-3.5 py-1.5 text-sm font-semibold text-turf-950 disabled:opacity-60">
                  <BrainCircuit size={16} aria-hidden="true" />
                  {busy ? 'Training' : 'Retrain on labeled kicks'}
                </button>
                <span className="chalk-text text-sm" role="status">
                  {msg || (status?.real_kicks_in_model ? `Model includes ${status.real_kicks_in_model} real kicks.` : 'Model currently learned from simulated kicks only.')}
                </span>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  )
}
