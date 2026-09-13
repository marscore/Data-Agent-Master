import type { Agent, Conversation, Meta, TraceRun, ChatEvent } from './types'

const BASE = (import.meta.env.VITE_API_BASE || '') + '/api/v1'

// Optional platform JWT (passed through to MCP servers). Stored in localStorage.
export function getToken(): string { return localStorage.getItem('aw_token') || '' }
export function setToken(t: string) { localStorage.setItem('aw_token', t) }

function headers(json = true): Record<string, string> {
  const h: Record<string, string> = {}
  if (json) h['Content-Type'] = 'application/json'
  const t = getToken()
  if (t) h['Authorization'] = `Bearer ${t}`
  return h
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, { ...init, headers: { ...headers(), ...(init?.headers || {}) } })
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail || detail } catch { /* ignore */ }
    throw new Error(`${r.status} ${detail}`)
  }
  return r.status === 204 ? (undefined as T) : r.json()
}

export const api = {
  meta: () => req<Meta>('/meta'),
  providers: (deep = false) => req<any>(`/health/providers?deep=${deep}`),

  listAgents: () => req<Agent[]>('/agents'),
  getAgent: (id: string) => req<Agent>(`/agents/${id}`),
  createAgent: (a: Agent) => req<Agent>('/agents', { method: 'POST', body: JSON.stringify(a) }),
  updateAgent: (id: string, patch: Partial<Agent>) => req<Agent>(`/agents/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteAgent: (id: string, dropIndex = false) => req<any>(`/agents/${id}?drop_index=${dropIndex}`, { method: 'DELETE' }),

  probe: (id: string) => req<any>(`/agents/${id}/mcp/probe`, { method: 'POST' }),
  tools: (id: string) => req<any>(`/agents/${id}/tools`),
  reindex: (id: string) => req<any>(`/agents/${id}/reindex`, { method: 'POST' }),
  ragStats: (id: string) => req<any>(`/agents/${id}/rag/stats`),

  traces: (agentId?: string) => req<TraceRun[]>(`/traces${agentId ? `?agent_id=${agentId}` : ''}`),
  trace: (runId: string) => req<TraceRun>(`/traces/${runId}`),

  conversations: () => req<Conversation[]>('/conversations'),
  conversation: (sid: string) => req<any>(`/conversations/${sid}`),
  deleteConversation: (sid: string) => req<any>(`/conversations/${sid}`, { method: 'DELETE' }),
}

// Streaming chat over SSE. Calls onEvent for each parsed event.
export async function chatStream(
  body: { agent_id: string; message: string; session_id?: string | null },
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(BASE + '/chat', {
    method: 'POST', headers: headers(), body: JSON.stringify(body), signal,
  })
  if (!r.ok || !r.body) throw new Error(`chat failed: ${r.status}`)
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data === '[DONE]') return
      try { onEvent(JSON.parse(data)) } catch { /* ignore partial */ }
    }
  }
}
