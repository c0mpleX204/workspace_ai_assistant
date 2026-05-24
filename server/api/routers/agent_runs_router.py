from fastapi import APIRouter, HTTPException

from server.api.schemas import AgentRunRequest, AgentRunStateResponse
from server.services.agent.run import create_agent_run_stream, load_agent_run


router = APIRouter(tags=["agent-runs"])


@router.post("/agent/runs/stream")
async def api_agent_run_stream(payload: AgentRunRequest):
    return create_agent_run_stream(payload)


@router.get("/agent/runs/{run_id}", response_model=AgentRunStateResponse)
def api_get_agent_run(run_id: str) -> AgentRunStateResponse:
    try:
        run = load_agent_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AgentRunStateResponse(**run)
