export interface McpSource {
  id: string
  url: string
  transport: 'jsonrpc_http' | 'streamable_http' | 'sse'
  label?: string
  auth_mode: 'passthrough' | 'static' | 'none'
  static_secret?: string
  header_name?: string
  header_prefix?: string
  allowed_tools?: string[]
  timeout?: number
  verify_tls?: boolean
  enabled: boolean
}

export interface Agent {
  id: string
  name: string
  description?: string
  enabled: boolean
  system_prompt?: string
  provider?: string
  model?: string
  max_tokens?: number
  routing_mode: 'supervisor' | 'react' | 'direct'
  max_tool_turns?: number
  rag_enabled: boolean
  rag_top_k?: number
  mcp_sources: McpSource[]
  created_at?: string
  updated_at?: string
}

export interface Meta {
  app: string; version: string; provider: string; llm_enabled: boolean
  chat_model: string
  embedding: { provider: string; model: string; dim: number }
  reranker: string; auth_mode: string; region: string
  checkpointer: string; vector_store: string
  transports: string[]; routing_modes: string[]
}

export interface TraceSpan { seq: number; kind: string; name: string; status: string; duration_ms: number; detail: any }
export interface TraceRun {
  run_id: string; agent_id: string; session_id: string; user_sub: string
  question: string; final_text: string; route: string; status: string
  error?: string; tokens_in: number; tokens_out: number; duration_ms: number
  started_at?: string; ended_at?: string; spans?: TraceSpan[]
}

export interface Conversation { session_id: string; agent_id: string; title: string; user_sub: string; updated_at?: string; message_count?: number }
export interface ChatEvent { type: string; [k: string]: any }
