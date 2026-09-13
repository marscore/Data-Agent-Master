import { useState } from 'react'
import { api } from '../api'
import type { Meta } from '../types'
import { useToast } from '../toast'

export default function Dashboard({ meta }: { meta: Meta | null }) {
  const toast = useToast()
  const [health, setHealth] = useState<any>(null)
  const [busy, setBusy] = useState(false)

  const deepCheck = async () => {
    setBusy(true)
    try { setHealth(await api.providers(true)); toast('已完成真实模型连通性检查') }
    catch (e: any) { toast(e.message, true) } finally { setBusy(false) }
  }

  if (!meta) return <div className="empty">连接后端中…（默认 http://localhost:8700）</div>
  const emb = meta.embedding
  return (
    <>
      <div className="h1">概览</div>
      <p className="sub">通用 AI Agent 平台 · MCP 联邦 · RAG · LangGraph · Bedrock / OpenAI 兼容</p>
      <div className="grid">
        <div className="card"><h3>LLM Provider</h3><div className="big">{meta.provider}</div><div className="muted mono">{meta.chat_model}</div></div>
        <div className="card"><h3>鉴权模式</h3><div className="big">{meta.auth_mode}</div><div className="muted">region {meta.region}</div></div>
        <div className="card"><h3>Embedding</h3><div className="big">{emb.provider}</div><div className="muted mono">{emb.model} · {emb.dim}d</div></div>
        <div className="card"><h3>Reranker</h3><div className="big">{meta.reranker}</div></div>
        <div className="card"><h3>向量库</h3><div className="big mono" style={{ fontSize: 15 }}>{meta.vector_store.includes('.db') ? 'milvus-lite' : 'milvus'}</div><div className="muted mono">{meta.vector_store}</div></div>
        <div className="card"><h3>记忆 Checkpointer</h3><div className="big">{meta.checkpointer}</div></div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="spread">
          <div><h3>真实模型连通性</h3><span className="muted">调用一次真实 embedding + chat 验证凭据</span></div>
          <button className="primary" onClick={deepCheck} disabled={busy}>{busy ? '检查中…' : '深度检查'}</button>
        </div>
        {health && (
          <div style={{ marginTop: 12 }} className="row">
            <span className={'chip ' + (health.embedding_check?.ok ? 'good' : 'bad')}>
              embedding {health.embedding_check?.ok ? `OK · ${health.embedding_check.dim}d` : 'FAIL'}
            </span>
            <span className={'chip ' + (health.chat_check?.ok ? 'good' : 'bad')}>
              chat {health.chat_check?.ok ? `OK · "${health.chat_check.sample}"` : 'FAIL'}
            </span>
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>支持的传输 / 路由</h3>
        <div className="row">
          {meta.transports.map(t => <span key={t} className="chip">{t}</span>)}
          <span className="faint">·</span>
          {meta.routing_modes.map(t => <span key={t} className="chip warn">{t}</span>)}
        </div>
      </div>
    </>
  )
}
