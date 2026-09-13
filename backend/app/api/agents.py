"""Agent config CRUD + MCP operations (probe / tools / reindex / rag stats).

This is the API the admin console uses to configure agent behavior: system
prompt, model, routing mode, RAG, and the per-agent MCP source registry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.mcp.federation import Federation, probe
from app.platform import repository
from app.platform.schemas import AgentIn, AgentPatch
from app.rag import indexer, vector_store
from app.shared.auth import Principal, get_principal

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents():
    return repository.list_agents()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    a = repository.get_agent(agent_id)
    if not a:
        raise HTTPException(404, "agent not found")
    return a


@router.post("/agents", status_code=201)
async def create_agent(body: AgentIn):
    try:
        return repository.create_agent(body)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentPatch):
    a = repository.update_agent(agent_id, body)
    if not a:
        raise HTTPException(404, "agent not found")
    return a


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, drop_index: bool = False):
    if drop_index:
        try:
            vector_store.drop(agent_id)
        except Exception:  # noqa: BLE001
            pass
    if not repository.delete_agent(agent_id):
        raise HTTPException(404, "agent not found")
    return {"deleted": agent_id}


def _require_agent(agent_id: str):
    a = repository.get_agent(agent_id)
    if not a:
        raise HTTPException(404, "agent not found")
    return a


@router.post("/agents/{agent_id}/mcp/probe")
async def probe_sources(agent_id: str, principal: Principal = Depends(get_principal)):
    agent = _require_agent(agent_id)
    sources = repository.to_mcp_sources(agent)
    results = [await probe(s, principal.access_token) for s in sources]
    return {"agent_id": agent_id, "sources": results}


@router.get("/agents/{agent_id}/tools")
async def list_tools(agent_id: str, principal: Principal = Depends(get_principal)):
    agent = _require_agent(agent_id)
    fed = Federation(repository.to_mcp_sources(agent), principal.access_token)
    tools = await fed.discover()
    return {"agent_id": agent_id,
            "tools": [{"flat_name": t.flat_name, "real_name": t.real_name,
                       "source": t.source.id, "description": t.description} for t in tools]}


@router.post("/agents/{agent_id}/reindex")
async def reindex(agent_id: str, principal: Principal = Depends(get_principal)):
    agent = _require_agent(agent_id)
    fed = Federation(repository.to_mcp_sources(agent), principal.access_token)
    return await indexer.reindex_from_mcp(agent_id, fed)


@router.get("/agents/{agent_id}/rag/stats")
async def rag_stats(agent_id: str):
    _require_agent(agent_id)
    return vector_store.stats(agent_id)


@router.post("/agents/{agent_id}/rag/documents")
async def add_documents(agent_id: str, docs: list[dict]):
    """Push arbitrary knowledge docs [{id,title,text,...}] into the agent's index."""
    _require_agent(agent_id)
    return indexer.index_documents(agent_id, docs)
