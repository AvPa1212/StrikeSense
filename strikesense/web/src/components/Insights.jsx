import { fmt } from '../lib/format.js'

export function Importance({ techniques }) {
  const rows = techniques ? [...techniques.importance].sort((a, b) => b.weight - a.weight) : []
  return (
    <section className="field p-5" aria-label="Which statistics matter most">
      <h2 className="font-display text-2xl font-semibold">What matters most</h2>
      <p className="chalk-text text-sm">How much each stat counts toward the score.</p>
      <ol className="mt-3 space-y-3">
        {rows.map((r, i) => (
          <li key={r.name}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-medium">{i + 1}. {r.name}</span>
              <span className="chalk-text text-sm">{Math.round(r.weight * 100)}%</span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-chalk/15">
              <div className="h-2 rounded-full bg-cone" style={{ width: `${(r.weight / rows[0].weight) * 100}%` }} />
            </div>
            <p className="chalk-text mt-1 text-xs leading-snug">{r.why}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function WorldCup({ context }) {
  if (!context || !context.by_technique) return null
  const rows = context.by_technique.filter((r) => r.shots >= 5)
  const top = Math.max(...rows.map((r) => r.goal_rate))
  return (
    <section className="field p-5" aria-label="World Cup shot context">
      <h2 className="font-display text-2xl font-semibold">How World Cup shots ended</h2>
      <p className="chalk-text text-sm">
        {fmt(context.shots)} open-play and free-kick shots from {context.matches} matches at {context.competition}.
        Share of each tagged technique that scored.
      </p>
      <ul className="mt-3 space-y-2.5">
        {rows.map((r) => (
          <li key={r.name} className="grid grid-cols-[6.5rem_1fr_auto] items-center gap-3 text-sm">
            <span>{r.name}</span>
            <div className="h-2 rounded-full bg-chalk/15">
              <div className="h-2 rounded-full bg-grass" style={{ width: `${(r.goal_rate / top) * 100}%` }} />
            </div>
            <span className="chalk-text whitespace-nowrap text-right">{fmt(r.goal_rate * 100, 1)}% of {r.shots}</span>
          </li>
        ))}
      </ul>
      <p className="chalk-text mt-3 text-xs">
        Small samples swing widely, so read lobs and volleys with care. Data: {context.source}.
      </p>
    </section>
  )
}
