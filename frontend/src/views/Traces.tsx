import { useEffect, useState } from 'react'
import { api } from '../api'
import type { TraceRun } from '../types'

export default function Traces() {
  const [runs, setRuns] = useState<TraceRun[]>([])
  const [sel, setSel] = useState<TraceRun | null>(null)

  const load = () => api.traces().then(setRuns).catch(() => {})
  useEffect(() => { load() }, [])
  const open = (id: string) => api.trace(id).then(setSel).catch(() => {})

  return (
    <>
      <div className="spread"><div className="h1">Traces</div><button onClick={load}>刷新</button></div>
      <p className="sub">每次运行的路由、工具调用、检索与耗时</p>
      <div className="split">
        <div>
          {runs.length === 0 && <div className="empty">暂无运行记录，去「对话演练」跑一条</div>}
          {runs.map(r => (
            <div key={r.run_id} className={'list-item' + (sel?.run_id === r.run_id ? ' sel' : '')} onClick={() => open(r.run_id)}>
              <div style={{ overflow: 'hidden' }}>
                <div style={{ whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{r.question || '(空)'}</div>
                <div className="faint mono" style={{ fontSize: 11 }}>{r.agent_id} · {r.route || '—'} · {r.duration_ms}ms</div>
              </div>
              <span className={'chip ' + (r.status === 'ok' ? 'good' : 'bad')}>{r.status}</span>
            </div>
          ))}
        </div>
        <div className="panel">
          {!sel ? <div className="empty">选择一条运行查看详情</div> : (
            <>
              <div className="spread"><b className="mono">{sel.run_id}</b><span className={'chip ' + (sel.status === 'ok' ? 'good' : 'bad')}>{sel.status}</span></div>
              <div className="muted" style={{ margin: '8px 0' }}>{sel.question}</div>
              <div className="row" style={{ fontSize: 12 }}>
                <span className="pill">route {sel.route}</span>
                <span className="pill">tokens in {sel.tokens_in} / out {sel.tokens_out}</span>
                <span className="pill">{sel.duration_ms}ms</span>
              </div>
              {sel.error && <div className="src" style={{ borderColor: 'var(--bad)', color: 'var(--bad)' }}>{sel.error}</div>}
              <hr />
              <h3 className="muted">Spans</h3>
              {(sel.spans || []).map(s => (
                <div key={s.seq} className="span">
                  <span className="faint">{s.seq}</span>
                  <span className={'kind ' + s.kind}>{s.kind}</span>
                  <span className="mono">{s.name}{s.detail?.source ? <span className="faint"> · {s.detail.source}</span> : null}</span>
                  <span className="faint">{s.duration_ms}ms</span>
                </div>
              ))}
              <hr />
              <details><summary className="muted">最终回答</summary><div style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{sel.final_text}</div></details>
            </>
          )}
        </div>
      </div>
    </>
  )
}
