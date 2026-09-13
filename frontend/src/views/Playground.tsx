import { useEffect, useRef, useState } from 'react'
import { api, chatStream } from '../api'
import type { Agent, ChatEvent } from '../types'
import { useToast } from '../toast'

interface Msg { role: 'user' | 'assistant'; text: string; tools: string[]; sources?: any[]; runId?: string; route?: string }

export default function Playground({ agentId }: { agentId?: string }) {
  const toast = useToast()
  const [agents, setAgents] = useState<Agent[]>([])
  const [agent, setAgent] = useState(agentId || '')
  const [session, setSession] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => { api.listAgents().then(a => { setAgents(a); if (!agent && a[0]) setAgent(a[0].id) }).catch(() => {}) }, [])
  useEffect(() => { if (agentId) setAgent(agentId) }, [agentId])
  useEffect(() => { scroller.current?.scrollTo(0, scroller.current.scrollHeight) }, [msgs])

  const reset = () => { setSession(null); setMsgs([]) }

  const send = async () => {
    const message = input.trim()
    if (!message || busy || !agent) return
    setInput(''); setBusy(true)
    setMsgs(m => [...m, { role: 'user', text: message, tools: [] },
                        { role: 'assistant', text: '', tools: [] }])
    const patch = (fn: (m: Msg) => void) => setMsgs(cur => {
      const copy = cur.slice(); fn(copy[copy.length - 1]); return copy
    })
    try {
      await chatStream({ agent_id: agent, message, session_id: session }, (e: ChatEvent) => {
        if (e.type === 'session') setSession(e.session_id)
        else if (e.type === 'status') patch(m => { if (e.tools || e.docs) m.tools.push(`↳ 准备：${e.tools} 个工具 · ${e.docs} 条检索`) })
        else if (e.type === 'tool_call') patch(m => m.tools.push(`→ 调用 ${e.tool}(${JSON.stringify(e.args).slice(0, 80)})`))
        else if (e.type === 'tool_result') patch(m => m.tools.push(`← ${e.tool} ${e.ok ? 'ok' : '失败'} · ${e.source || ''} ${e.latency_ms || 0}ms`))
        else if (e.type === 'token') patch(m => { m.text += e.content })
        else if (e.type === 'answer_end') patch(m => { m.sources = e.sources; m.runId = e.run_id; m.route = e.route })
        else if (e.type === 'error') patch(m => { m.text += `\n[错误] ${e.message}` })
      })
    } catch (e: any) { toast(e.message, true) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="spread">
        <div className="h1">对话演练</div>
        <div className="row">
          <select value={agent} onChange={e => { setAgent(e.target.value); reset() }} style={{ width: 220 }}>
            {agents.map(a => <option key={a.id} value={a.id}>{a.name}（{a.id}）</option>)}
          </select>
          <button onClick={reset}>新会话</button>
        </div>
      </div>
      <p className="sub">流式对话 · 实时展示路由、MCP 工具调用与来源 {session && <span className="mono faint">· {session}</span>}</p>

      <div className="chat panel">
        <div className="msgs" ref={scroller}>
          {msgs.length === 0 && <div className="empty">试试：「本月的月活跃用户 MAU 是多少？」</div>}
          {msgs.map((m, i) => (
            <div key={i} className={'msg ' + m.role}>
              {m.tools.length > 0 && <div className="tools">{m.tools.map((t, j) => <div key={j} className="tool-line">{t}</div>)}</div>}
              {m.text && <div className="bubble">{m.text}{busy && i === msgs.length - 1 && <span className="faint">▋</span>}</div>}
              {m.route && <div className="row" style={{ marginTop: 6 }}>
                <span className="pill">route {m.route}</span>
                {m.runId && <span className="pill mono">trace {m.runId}</span>}
              </div>}
              {m.sources && m.sources.length > 0 && (
                <div style={{ marginTop: 6 }}>
                  <div className="faint" style={{ fontSize: 11 }}>来源</div>
                  {m.sources.map((s: any, j: number) => <div key={j} className="src">{s.title} <span className="faint">({s.rerank_score ?? s.score})</span></div>)}
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="composer">
          <textarea rows={2} value={input} placeholder="输入问题，Enter 发送 / Shift+Enter 换行"
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
          <button className="primary" onClick={send} disabled={busy || !agent}>{busy ? '…' : '发送'}</button>
        </div>
      </div>
    </>
  )
}
