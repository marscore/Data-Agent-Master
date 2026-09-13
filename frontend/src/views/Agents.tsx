import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Agent, McpSource, Meta } from '../types'
import { useToast } from '../toast'

const BLANK_SOURCE: McpSource = {
  id: '', url: '', transport: 'jsonrpc_http', label: '', auth_mode: 'passthrough',
  static_secret: '', enabled: true,
}
function blankAgent(): Agent {
  return { id: '', name: '', description: '', enabled: true, system_prompt: '',
    provider: '', model: '', max_tokens: 0, routing_mode: 'supervisor',
    max_tool_turns: 0, rag_enabled: true, rag_top_k: 0, mcp_sources: [] }
}

export default function Agents({ meta, onPlay }: { meta: Meta | null; onPlay: (id: string) => void }) {
  const toast = useToast()
  const [agents, setAgents] = useState<Agent[]>([])
  const [sel, setSel] = useState<Agent | null>(null)
  const [isNew, setIsNew] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [busy, setBusy] = useState('')

  const load = () => api.listAgents().then(setAgents).catch(e => toast(e.message, true))
  useEffect(() => { load() }, [])

  const edit = (a: Agent) => { setSel(JSON.parse(JSON.stringify(a))); setIsNew(false); setResult(null) }
  const create = () => { setSel(blankAgent()); setIsNew(true); setResult(null) }
  const set = (k: keyof Agent, v: any) => setSel(s => s ? { ...s, [k]: v } : s)

  const setSrc = (i: number, k: keyof McpSource, v: any) =>
    setSel(s => { if (!s) return s; const src = s.mcp_sources.slice(); (src[i] as any)[k] = v; return { ...s, mcp_sources: src } })
  const addSrc = () => setSel(s => s ? { ...s, mcp_sources: [...s.mcp_sources, { ...BLANK_SOURCE }] } : s)
  const rmSrc = (i: number) => setSel(s => s ? { ...s, mcp_sources: s.mcp_sources.filter((_, j) => j !== i) } : s)

  const save = async () => {
    if (!sel) return
    if (!sel.id || !sel.name) return toast('id 和 name 必填', true)
    setBusy('save')
    try {
      if (isNew) { await api.createAgent(sel); toast('已创建') }
      else { await api.updateAgent(sel.id, sel); toast('已保存') }
      setIsNew(false); await load()
    } catch (e: any) { toast(e.message, true) } finally { setBusy('') }
  }
  const op = async (name: string, fn: () => Promise<any>) => {
    setBusy(name); setResult(null)
    try { setResult(await fn()); toast(`${name} 完成`) }
    catch (e: any) { toast(e.message, true) } finally { setBusy('') }
  }
  const del = async () => {
    if (!sel || isNew) return
    if (!confirm(`删除 agent "${sel.id}"？`)) return
    try { await api.deleteAgent(sel.id, true); toast('已删除'); setSel(null); await load() }
    catch (e: any) { toast(e.message, true) }
  }

  return (
    <>
      <div className="spread"><div className="h1">Agents</div><button className="primary" onClick={create}>+ 新建 Agent</button></div>
      <p className="sub">配置具体的 agent 行为：system prompt、模型、路由方式、RAG 与 MCP 工具源</p>
      <div className="split">
        <div>
          {agents.map(a => (
            <div key={a.id} className={'list-item' + (sel?.id === a.id && !isNew ? ' sel' : '')} onClick={() => edit(a)}>
              <div>
                <div>{a.name} {!a.enabled && <span className="chip">停用</span>}</div>
                <div className="faint mono" style={{ fontSize: 11 }}>{a.id} · {a.routing_mode} · {a.mcp_sources.length} MCP</div>
              </div>
              <span className="pill">{a.rag_enabled ? 'RAG' : ''}</span>
            </div>
          ))}
        </div>

        <div className="panel">
          {!sel ? <div className="empty">选择或新建一个 Agent</div> : (
            <>
              <div className="field-row">
                <div><label>ID</label><input value={sel.id} disabled={!isNew} onChange={e => set('id', e.target.value)} /></div>
                <div><label>名称</label><input value={sel.name} onChange={e => set('name', e.target.value)} /></div>
              </div>
              <label>描述</label><input value={sel.description} onChange={e => set('description', e.target.value)} />
              <label>System Prompt</label>
              <textarea rows={5} value={sel.system_prompt} onChange={e => set('system_prompt', e.target.value)} />

              <div className="field-row">
                <div><label>Provider（留空=继承 {meta?.provider}）</label>
                  <select value={sel.provider} onChange={e => set('provider', e.target.value)}>
                    <option value="">继承</option><option value="bedrock">bedrock</option><option value="openai">openai</option>
                  </select></div>
                <div><label>模型（留空=继承 {meta?.chat_model}）</label><input value={sel.model} onChange={e => set('model', e.target.value)} /></div>
              </div>
              <div className="field-row">
                <div><label>路由方式</label>
                  <select value={sel.routing_mode} onChange={e => set('routing_mode', e.target.value)}>
                    <option value="supervisor">supervisor（LLM 路由）</option>
                    <option value="react">react（总是用工具）</option>
                    <option value="direct">direct（直答）</option>
                  </select></div>
                <div><label>最大工具轮数（0=默认）</label><input type="number" value={sel.max_tool_turns} onChange={e => set('max_tool_turns', +e.target.value)} /></div>
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                <label style={{ margin: 0 }}><input type="checkbox" style={{ width: 'auto' }} checked={sel.enabled} onChange={e => set('enabled', e.target.checked)} /> 启用</label>
                <label style={{ margin: 0 }}><input type="checkbox" style={{ width: 'auto' }} checked={sel.rag_enabled} onChange={e => set('rag_enabled', e.target.checked)} /> RAG 检索</label>
                <span className="muted">top_k</span>
                <input type="number" style={{ width: 70 }} value={sel.rag_top_k} onChange={e => set('rag_top_k', +e.target.value)} />
              </div>

              <hr />
              <div className="spread"><h3 className="muted" style={{ margin: 0 }}>MCP 工具源</h3><button onClick={addSrc}>+ 添加源</button></div>
              {sel.mcp_sources.map((s, i) => (
                <div key={i} className="mcp-src">
                  <div className="field-row">
                    <div><label>源 ID</label><input value={s.id} onChange={e => setSrc(i, 'id', e.target.value)} /></div>
                    <div><label>标签</label><input value={s.label} onChange={e => setSrc(i, 'label', e.target.value)} /></div>
                  </div>
                  <label>URL</label><input className="mono" value={s.url} onChange={e => setSrc(i, 'url', e.target.value)} />
                  <div className="field-row">
                    <div><label>传输</label>
                      <select value={s.transport} onChange={e => setSrc(i, 'transport', e.target.value)}>
                        <option value="jsonrpc_http">jsonrpc_http（data-master）</option>
                        <option value="streamable_http">streamable_http</option>
                        <option value="sse">sse</option>
                      </select></div>
                    <div><label>鉴权</label>
                      <select value={s.auth_mode} onChange={e => setSrc(i, 'auth_mode', e.target.value)}>
                        <option value="passthrough">passthrough（透传 JWT）</option>
                        <option value="static">static（固定密钥）</option>
                        <option value="none">none</option>
                      </select></div>
                  </div>
                  {s.auth_mode === 'static' && (<><label>Static Secret</label><input value={s.static_secret} onChange={e => setSrc(i, 'static_secret', e.target.value)} /></>)}
                  <div className="spread" style={{ marginTop: 8 }}>
                    <label style={{ margin: 0 }}><input type="checkbox" style={{ width: 'auto' }} checked={s.enabled} onChange={e => setSrc(i, 'enabled', e.target.checked)} /> 启用此源</label>
                    <button className="danger ghost" onClick={() => rmSrc(i)}>移除</button>
                  </div>
                </div>
              ))}

              <hr />
              <div className="row">
                <button className="primary" onClick={save} disabled={busy === 'save'}>{busy === 'save' ? '保存中…' : '保存'}</button>
                {!isNew && <>
                  <button onClick={() => op('探活', () => api.probe(sel.id))} disabled={!!busy}>探活 MCP</button>
                  <button onClick={() => op('工具', () => api.tools(sel.id))} disabled={!!busy}>列出工具</button>
                  <button onClick={() => op('重建索引', () => api.reindex(sel.id))} disabled={!!busy}>重建 RAG 索引</button>
                  <button onClick={() => op('索引统计', () => api.ragStats(sel.id))} disabled={!!busy}>索引统计</button>
                  <button onClick={() => onPlay(sel.id)}>去演练 →</button>
                  <button className="danger" onClick={del}>删除</button>
                </>}
              </div>
              {result && <pre className="mono" style={{ marginTop: 12, background: 'var(--bg)', padding: 12, borderRadius: 8, maxHeight: 260, overflow: 'auto', border: '1px solid var(--border)' }}>{JSON.stringify(result, null, 2)}</pre>}
            </>
          )}
        </div>
      </div>
    </>
  )
}
