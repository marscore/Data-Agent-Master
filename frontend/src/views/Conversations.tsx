import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Conversation } from '../types'

export default function Conversations() {
  const [convs, setConvs] = useState<Conversation[]>([])
  const [sel, setSel] = useState<any>(null)
  const load = () => api.conversations().then(setConvs).catch(() => {})
  useEffect(() => { load() }, [])
  return (
    <>
      <div className="spread"><div className="h1">会话记忆</div><button onClick={load}>刷新</button></div>
      <p className="sub">落库的多轮对话历史（每轮作为上下文回灌给 agent）</p>
      <div className="split">
        <div>
          {convs.length === 0 && <div className="empty">暂无会话</div>}
          {convs.map(c => (
            <div key={c.session_id} className={'list-item' + (sel?.session_id === c.session_id ? ' sel' : '')}
              onClick={() => api.conversation(c.session_id).then(setSel)}>
              <div style={{ overflow: 'hidden' }}>
                <div style={{ whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{c.title || '(空)'}</div>
                <div className="faint mono" style={{ fontSize: 11 }}>{c.agent_id} · {c.message_count} 条</div>
              </div>
            </div>
          ))}
        </div>
        <div className="panel">
          {!sel ? <div className="empty">选择一个会话</div> : (
            <>
              <div className="spread"><b className="mono">{sel.session_id}</b>
                <button className="danger" onClick={() => api.deleteConversation(sel.session_id).then(() => { setSel(null); load() })}>删除</button></div>
              <hr />
              {(sel.messages || []).map((m: any, i: number) => (
                <div key={i} className={'msg ' + m.role} style={{ maxWidth: '100%' }}>
                  <div className="faint" style={{ fontSize: 11 }}>{m.role}</div>
                  <div className="bubble">{m.content}</div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </>
  )
}
