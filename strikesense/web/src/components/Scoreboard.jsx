import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Volume2 } from 'lucide-react'
import { api } from '../lib/useStrikeSense.js'
import { TECH_LABEL, fmt, scoreColor } from '../lib/format.js'

function ScoreRing({ score }) {
  const r = 82
  const c = 2 * Math.PI * r
  const has = score !== null && score !== undefined
  const pct = has ? Math.max(0, Math.min(100, score)) / 100 : 0
  return (
    <svg viewBox="0 0 220 220" className="h-[210px] w-[210px] shrink-0" role="img"
      aria-label={has ? `Match to benchmark ${Math.round(score)} out of 100` : 'No score yet'}>
      <circle cx="110" cy="110" r={r} fill="none" stroke="#f2f5ec" strokeOpacity="0.22" strokeWidth="6" />
      <line x1="16" y1="110" x2="204" y2="110" stroke="#f2f5ec" strokeOpacity="0.16" strokeWidth="2" />
      <circle
        cx="110" cy="110" r={r} fill="none" stroke={scoreColor(score)} strokeWidth="9" strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`} transform="rotate(-90 110 110)"
        style={{ transition: 'stroke-dasharray 700ms cubic-bezier(.2,.8,.2,1)' }}
      />
      <text x="110" y="122" textAnchor="middle" fontFamily="Big Shoulders Display" fontWeight="800"
        fontSize="84" fill="#f2f5ec">{has ? Math.round(score) : '--'}</text>
      <text x="110" y="150" textAnchor="middle" fontFamily="Barlow" fontSize="13" fill="#f2f5ec" fillOpacity="0.66">
        match to benchmark
      </text>
    </svg>
  )
}

function Coach({ kick }) {
  const [fb, setFb] = useState(null)
  const [voice, setVoice] = useState('idle')
  const audioRef = useRef(null)

  useEffect(() => {
    setFb(null)
    setVoice('idle')
    if (!kick) return
    let alive = true
    api(`/api/kicks/${kick.id}/coach`).then((d) => alive && setFb(d)).catch(() => {})
    return () => {
      alive = false
      audioRef.current?.pause()
      window.speechSynthesis?.cancel()
    }
  }, [kick?.id])

  const speak = async () => {
    if (!fb) return
    setVoice('loading')
    try {
      const res = await fetch(`/api/kicks/${kick.id}/voice`)
      if (res.ok) {
        const url = URL.createObjectURL(await res.blob())
        const a = new Audio(url)
        audioRef.current = a
        a.onended = () => setVoice('idle')
        await a.play()
        setVoice('playing')
        return
      }
    } catch {
      /* fall through to browser speech */
    }
    if ('speechSynthesis' in window) {
      const u = new SpeechSynthesisUtterance(fb.text)
      u.onend = () => setVoice('idle')
      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(u)
      setVoice('playing')
    } else {
      setVoice('idle')
    }
  }

  return (
    <div className="min-w-[260px] flex-1 basis-[280px]">
      <h2 className="font-display text-2xl font-semibold">Coach</h2>
      {!kick && <p className="chalk-text mt-2 max-w-[38ch]">Feedback appears here after your first kick.</p>}
      {kick && !fb && <p className="chalk-text mt-2">Reading the kick.</p>}
      {fb && (
        <>
          <p className="mt-2 max-w-[54ch] text-[17px] leading-snug">{fb.text}</p>
          <div className="mt-3 flex items-center gap-4">
            <button
              onClick={speak}
              disabled={voice === 'loading'}
              className="flex items-center gap-2 whitespace-nowrap rounded-md border border-chalk/50 px-3 py-1.5 text-sm font-semibold hover:border-chalk disabled:opacity-60"
            >
              <Volume2 size={16} aria-hidden="true" />
              {voice === 'loading' ? 'Loading voice' : voice === 'playing' ? 'Speaking' : 'Hear it'}
            </button>
            <span className="chalk-text text-sm">
              {fb.source === 'gemini' ? 'Written by Gemini' : 'Rule-based coach. Add a Gemini key for richer notes.'}
            </span>
          </div>
        </>
      )}
    </div>
  )
}

export default function Scoreboard({ kick, count }) {
  const mismatch = kick && kick.target !== 'auto' && kick.predicted !== kick.target && kick.confidence > 0.6
  const top = kick
    ? Object.entries(kick.probs).sort((a, b) => b[1] - a[1]).slice(0, 3)
    : []

  return (
    <section className="boxed flex flex-wrap items-center gap-x-10 gap-y-6 px-5 py-6 sm:px-8" aria-label="Latest kick">
      <div className="min-w-[280px] flex-1 basis-[300px]">
        <p className="chalk-text text-sm">{kick ? `Kick ${count}` : 'Ready'}</p>
        <h2 className="mt-1 font-display text-[clamp(2.6rem,6vw,4.4rem)] font-extrabold leading-[0.95]">
          {kick ? TECH_LABEL[kick.technique] : 'Waiting for a kick'}
        </h2>
        {!kick && (
          <p className="chalk-text mt-3 max-w-[36ch]">
            Place the ball with the marked side facing you, then strike it. In simulator mode, press Simulate kick.
          </p>
        )}
        {mismatch && (
          <p className="mt-3 flex items-center gap-2 text-card">
            <AlertTriangle size={17} aria-hidden="true" />
            You aimed for a {TECH_LABEL[kick.target].toLowerCase()}. The network read a {TECH_LABEL[kick.predicted].toLowerCase()}.
          </p>
        )}
        {kick && (
          <div className="mt-4 max-w-[340px] space-y-1.5" aria-label="Network read">
            {top.map(([k, p]) => (
              <div key={k} className="flex items-center gap-3 text-sm">
                <span className="w-32 truncate">{TECH_LABEL[k]}</span>
                <div className="h-2 flex-1 rounded-full bg-chalk/15">
                  <div className="h-2 rounded-full bg-chalk" style={{ width: `${Math.max(2, p * 100)}%` }} />
                </div>
                <span className="w-10 text-right">{fmt(p * 100)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <ScoreRing score={kick?.overall} />
      <Coach kick={kick} />
    </section>
  )
}
