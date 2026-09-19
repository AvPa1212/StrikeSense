import { useCallback, useEffect, useRef, useState } from 'react'

const MAX_LIVE = 3000 // 6 seconds at 500 Hz

async function api(path, options) {
  const res = await fetch(path, options)
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.json()
}

const post = (path, body) =>
  api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })

export function useStrikeSense() {
  const [status, setStatus] = useState(null)
  const [connected, setConnected] = useState(false)
  const [kicks, setKicks] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [techniques, setTechniques] = useState(null)
  const [context, setContext] = useState(null)
  const [pulse, setPulse] = useState(0)
  const live = useRef([]) // [{t, a:[3], g:[3], f:[4]}]

  useEffect(() => {
    api('/api/kicks')
      .then((k) => {
        setKicks(k)
        if (k.length) setSelectedId(k[k.length - 1].id)
      })
      .catch(() => {})
    api('/api/techniques').then(setTechniques).catch(() => {})
    api('/api/context').then(setContext).catch(() => {})
  }, [])

  useEffect(() => {
    let ws
    let timer
    let closed = false
    const open = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) timer = setTimeout(open, 1200)
      }
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data)
        if (m.type === 'samples') {
          const buf = live.current
          for (let i = 0; i < m.t.length; i++) buf.push({ t: m.t[i], a: m.a[i], g: m.g[i], f: m.f[i] })
          if (buf.length > MAX_LIVE) buf.splice(0, buf.length - MAX_LIVE)
        } else if (m.type === 'status') {
          setStatus(m)
        } else if (m.type === 'kick') {
          setKicks((prev) => (prev.some((k) => k.id === m.kick.id) ? prev : [...prev, m.kick]))
          setSelectedId(m.kick.id)
          setPulse((p) => p + 1)
        }
      }
    }
    open()
    return () => {
      closed = true
      clearTimeout(timer)
      ws && ws.close()
    }
  }, [])

  const setTarget = useCallback(async (technique) => {
    setStatus((s) => (s ? { ...s, target: technique } : s))
    await post('/api/target', { technique })
  }, [])

  const simulate = useCallback((technique, level) => {
    const q = new URLSearchParams()
    if (technique) q.set('technique', technique)
    q.set('level', level || 'good')
    return post(`/api/sim/kick?${q}`)
  }, [])

  const newSession = useCallback(async () => {
    await post('/api/session/new')
    setKicks([])
    setSelectedId(null)
  }, [])

  const labelKick = useCallback(async (id, technique) => {
    await post(`/api/kicks/${id}/label`, { technique })
    setKicks((prev) => prev.map((k) => (k.id === id ? { ...k, label: technique } : k)))
  }, [])

  const retrain = useCallback(async () => {
    const r = await post('/api/model/retrain')
    setStatus((s) => (s ? { ...s, real_kicks_in_model: r.real_kicks } : s))
    return r
  }, [])

  const selected = kicks.find((k) => k.id === selectedId) || null

  return {
    status, connected, kicks, selected, selectedId, selectKick: setSelectedId,
    techniques, context, pulse, live, setTarget, simulate, newSession, labelKick, retrain,
  }
}

export { api }
