# AgentWorks — 通用 AI Agent 平台

把平台的 AI 能力从 data-master 单体里拆出来的独立项目。它是一个**通用的、可配置的 AI Agent 平台**：
通过 **MCP 联邦**消费本平台（data-master `/api/mcp`）与外部系统（OpenMetadata、Superset 等）的工具，
用 **LangGraph** 编排，具备 **RAG 检索**、**会话记忆**与**运行 trace**，模型走 **AWS Bedrock**（Anthropic 原生 Messages API + Cohere embed/rerank），
同时兼容任意 **OpenAI 兼容**接口。data-master「数据问数」只是平台上的一个 agent，平台本身不与其绑定。

前后端分离：`backend/`（FastAPI 服务）与 `frontend/`（管理控制台）是各自独立的可部署单元。

## 能力

- **MCP 联邦**：可配置的 MCP 注册表（每个 agent 一份），支持三种传输：`jsonrpc_http`（data-master 的 `POST /api/mcp`）、`streamable_http`、`sse`。跨源工具名冲突自动命名空间化，身份（平台 JWT）透传到每个 MCP，平台不做鉴权决策。
- **LangGraph 编排**：`prepare → supervisor → {agent | rag | direct | clarify} → finalize`。`agent` 节点内跑受限的 ReAct 工具循环。routing_mode 可选 `supervisor`（LLM 路由）/`react`（总是用工具）/`direct`（直答）。
- **RAG**：查询改写 → 向量检索（Milvus / milvus-lite）→ Cohere 重排 → 阈值过滤。索引可从 agent 的 MCP 工具（如 `list_metrics`/`get_metric`）自动构建。
- **记忆**：会话历史落库（Postgres/SQLite）并在每轮作为上下文回灌；LangGraph checkpointer 提供线程内图状态记忆。
- **Trace**：每次运行记录节点/检索/路由/工具/LLM 的 span，可经 API 与控制台查看。
- **模型**：Bedrock（`global.anthropic.claude-sonnet-5` 等，SigV4 或 bearer 鉴权）；embed=`cohere.embed-v4`，rerank=`cohere.rerank-v3.5`。或任意 OpenAI 兼容端点。
- **管理控制台**：配置 agent 行为（system prompt、模型、路由、RAG、MCP 源）、探活/查看工具、重建索引、对话演练、查看 trace 与会话。

## 目录

```
backend/    FastAPI 服务（app/：llm, embeddings, mcp, rag, agents, memory, trace, api, platform）
frontend/   管理控制台（独立前端，调用 backend API）
```

## 快速开始（本地）

需要可用的 AWS 凭据（Bedrock）。本地用 SSO 角色时 `BEDROCK_ANTHROPIC_AUTH_MODE=sigv4`。

```bash
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env            # 按需修改；默认 Bedrock + milvus-lite + sqlite

# 1) 起一个 mock data-master MCP（无需 Java 后端即可跑通全链路）
AWS_PROFILE=<你的profile> ./.venv/bin/python -m uvicorn scripts.mock_mcp_server:app --port 8790 &

# 2) 起后端
AWS_PROFILE=<你的profile> AWS_REGION=ap-southeast-1 ./.venv/bin/python -m uvicorn app.main:app --port 8700

# 3) 端到端冒烟（真实 Bedrock）
AWS_PROFILE=<你的profile> ./.venv/bin/python scripts/smoke.py
```

对接**真实 data-master**：把 `data-master` agent 的 MCP 源 URL 指向真实的 `http://<host>:18888/api/mcp`（默认已配置），
携带平台 JWT 调用即可（透传给 data-master 校验）。

前端：见 `frontend/README.md`（`npm install && npm run dev`，默认连 `http://localhost:8700`）。

## 关键配置（backend/.env）

| 变量 | 说明 |
|---|---|
| `LLM_PROVIDER` | `bedrock` 或 `openai` |
| `BEDROCK_CHAT_MODEL` | 如 `global.anthropic.claude-sonnet-5` |
| `BEDROCK_ANTHROPIC_AUTH_MODE` | `sigv4`（本地 SSO）/ `bearer`（QA/生产） |
| `BEDROCK_EMBEDDING_MODEL` / `BEDROCK_RERANKER_MODEL` | Cohere embed-v4 / rerank-v3.5 |
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_CHAT_MODEL` | OpenAI 兼容端点 |
| `VECTOR_DB_URI` | `*.db` 文件 = milvus-lite；否则 Milvus 服务 URI |
| `DATABASE_URL` | 平台配置/记忆/trace 存储（sqlite 默认，或 Postgres） |
| `PLATFORM_JWT_SECRET` / `ALLOW_ANONYMOUS` | 身份校验（本地可匿名） |

## 契约

消费 data-master 的 MCP（`docs/ai-assistant-standalone-plan.md`）：`POST /api/mcp` JSON-RPC 2.0，
`tools/list` 返回 `{name,description,inputSchema}`，`tools/call` 返回 `{content:[{type:"text",text}]}`，Bearer JWT 鉴权。
