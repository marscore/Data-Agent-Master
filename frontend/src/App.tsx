import { useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'
import type { Meta } from './types'
import { ToastProvider } from './toast'
import Dashboard from './views/Dashboard'
import Agents from './views/Agents'
import Playground from './views/Playground'
import Traces from './views/Traces'
import Conversations from './views/Conversations'

type View = 'dashboard' | 'agents' | 'playground' | 'traces' | 'conversations'
const NAV: [View, string][] = [
  ['dashboard', '概览'], ['agents', 'Agents'], ['playground', '对话演练'],
  ['traces', 'Traces'], ['conversations', '会话记忆'],
]

export default function App() {
  const [view, setView] = useState<View>('dashboard')
  const [meta, setMeta] = useState<Meta | null>(null)
  const [token, setTok] = useState(getToken())
  const [playgroundAgent, setPlaygroundAgent] = useState<string | undefined>()

  useEffect(() => { api.meta().then(setMeta).catch(() => {}) }, [])

  const goPlayground = (agentId: string) => { setPlaygroundAgent(agentId); setView('playground') }

  return (
    <ToastProvider>
      <div className="app">
        <aside className="side">
          <div className="brand">Data Agent<span> Master</span></div>
          <nav className="nav">
            {NAV.map(([v, label]) => (
              <button key={v} className={view === v ? 'active' : ''} onClick={() => setView(v)}>{label}</button>
            ))}
          </nav>
          <div className="foot">
            <label>平台 JWT（透传给 MCP，可选）</label>
            <input value={token} placeholder="Bearer token…" onChange={e => setTok(e.target.value)}
              onBlur={() => setToken(token)} />
            <div style={{ marginTop: 10 }}>
              {meta ? <>v{meta.version} · {meta.provider} · {meta.auth_mode}</> : '连接中…'}
            </div>
          </div>
        </aside>
        <main className="main">
          {view === 'dashboard' && <Dashboard meta={meta} />}
          {view === 'agents' && <Agents meta={meta} onPlay={goPlayground} />}
          {view === 'playground' && <Playground agentId={playgroundAgent} />}
          {view === 'traces' && <Traces />}
          {view === 'conversations' && <Conversations />}
        </main>
      </div>
    </ToastProvider>
  )
}
