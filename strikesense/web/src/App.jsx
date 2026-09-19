import { useState } from 'react'
import TopBar from './components/TopBar.jsx'
import Scoreboard from './components/Scoreboard.jsx'
import BallMap from './components/BallMap.jsx'
import LiveTrace from './components/LiveTrace.jsx'
import Metrics from './components/Metrics.jsx'
import Session from './components/Session.jsx'
import { Importance, WorldCup } from './components/Insights.jsx'
import SensorsPage from './components/SensorsPage.jsx'
import { useStrikeSense } from './lib/useStrikeSense.js'

export default function App() {
  const [page, setPage] = useState('pitch')
  const s = useStrikeSense()
  const bench = s.selected && s.techniques ? s.techniques.benchmarks[s.selected.technique] : null
  const count = s.selected ? s.kicks.findIndex((k) => k.id === s.selected.id) + 1 : 0

  return (
    <div className="min-h-screen">
      <TopBar
        page={page} setPage={setPage} status={s.status} connected={s.connected}
        setTarget={s.setTarget} simulate={s.simulate} newSession={s.newSession}
      />
      <main className="mx-auto max-w-[1280px] px-5 py-6">
        {page === 'pitch' ? (
          <div className="space-y-5">
            <Scoreboard kick={s.selected} count={count} />
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(320px,400px)_1fr]">
              <BallMap kick={s.selected} bench={bench} pulse={s.pulse} />
              <div className="space-y-5">
                <LiveTrace live={s.live} />
                <Metrics kick={s.selected} />
              </div>
            </div>
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <Session
                kicks={s.kicks} selected={s.selected} selectKick={s.selectKick}
                labelKick={s.labelKick} retrain={s.retrain} status={s.status}
              />
              <div className="space-y-5">
                <Importance techniques={s.techniques} />
                <WorldCup context={s.context} />
              </div>
            </div>
          </div>
        ) : (
          <SensorsPage live={s.live} kicks={s.kicks} selectedId={s.selectedId} />
        )}
      </main>
    </div>
  )
}
