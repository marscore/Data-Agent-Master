# Data Agent Master Frontend (管理控制台)

独立的前端（Vite + React + TypeScript），通过 HTTP 调用后端 API。与后端分离部署。

## 运行

```bash
npm install
npm run dev            # http://localhost:5273 ，dev 代理 /api -> http://localhost:8700
```

改后端地址：`VITE_API_TARGET=http://host:8700 npm run dev`，或构建时设 `VITE_API_BASE`。

## 视图

- **概览**：模型/鉴权/向量库/记忆配置；一键真实模型连通性检查。
- **Agents**：配置 agent 行为（system prompt、模型、路由方式、RAG、MCP 工具源）；探活/列工具/重建索引。
- **对话演练**：流式对话，实时展示路由、MCP 工具调用与来源、trace id。
- **Traces**：运行的路由/工具/检索/耗时 span。
- **会话记忆**：多轮历史。

## 构建

```bash
npm run build          # 产物在 dist/（后端存在时会自动挂载在 / ）
```
