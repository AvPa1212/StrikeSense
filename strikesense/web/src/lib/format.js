export const TECH_LABEL = {
  drive: 'Driven shot',
  curl: 'Curled shot',
  chip: 'Chip',
  pass: 'Inside-foot pass',
  knuckle: 'Knuckleball',
}

export function fmt(v, digits = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a'
  const n = Math.abs(v) < 0.5 * 10 ** -digits ? 0 : Number(v)
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function scoreTone(s) {
  if (s === null || s === undefined) return 'text-chalk/50'
  if (s >= 80) return 'text-grass'
  if (s >= 55) return 'text-card'
  return 'text-flag'
}

export function scoreColor(s) {
  if (s === null || s === undefined) return '#f2f5ec80'
  if (s >= 80) return '#8fe08a'
  if (s >= 55) return '#ffd23f'
  return '#ff5a4d'
}

export function spinWords(side) {
  if (Math.abs(side) < 150) return 'almost no curl'
  return side > 0 ? 'curls left' : 'curls right'
}

export function timeOf(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
