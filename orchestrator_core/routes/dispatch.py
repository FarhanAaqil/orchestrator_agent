"""
orchestrator_core/routes/dispatch.py

POST /dispatch — classify a command and execute it against the resolved agent.
Returns AgentResult directly. Raises ClarificationNeeded as 422 when confidence is low.
"""

import logging
import time
from fastapi import APIRouter
from pydantic import BaseModel

from orchestrator_core.core.router import classify
from orchestrator_core.models import RouterResult, ClarificationNeeded, AgentResult, ErrorResponse
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dispatch", tags=["Routing"])

# ── Agent registry ─────────────────────────────────────────────────────────────
# Maps agent name (as returned by classify) to its handle() function.
# Import lazily inside the function to avoid circular imports.

def _get_agent_registry() -> dict:
    from orchestrator_core.agents import career_agent, research_agent, growth_content_agent, critic_agent
    return {
        "career_agent": career_agent.handle,
        "research_agent": research_agent.handle,
        "growth_content_agent": growth_content_agent.handle,
        "critic_agent": critic_agent.handle,
    }


class DispatchRequest(BaseModel):
    command: str
    context: dict = {}


@router.post("", response_model=None)
async def dispatch_command(body: DispatchRequest):
    """
    Classify and immediately execute a command.

    Returns AgentResult on success.
    Returns 422 with ClarificationNeeded body when confidence is too low.
    Returns 400 if the classified agent is not in the registry.
    """
    t_start = time.monotonic()
    logger.info("Dispatching command: %.80s", body.command)

    classification = classify(body.command)

    if isinstance(classification, ClarificationNeeded):
        logger.info("Dispatch blocked — clarification needed: %s", classification.candidates)
        return JSONResponse(
            status_code=422,
            content=classification.model_dump(),
        )

    assert isinstance(classification, RouterResult)
    agent_name = classification.agent
    registry = _get_agent_registry()

    if agent_name not in registry:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error="AGENT_NOT_FOUND",
                detail=f"Agent '{agent_name}' is not registered in the dispatch registry.",
            ).model_dump(),
        )

    handler = registry[agent_name]
    result: AgentResult = handler(body.command, metadata={"context": body.context})

    latency_ms = int((time.monotonic() - t_start) * 1000)
    logger.info(
        "Dispatch complete — agent=%s confidence=%.2f latency_ms=%d",
        agent_name,
        classification.confidence,
        latency_ms,
    )

    result.metadata["latency_ms"] = latency_ms
    result.metadata["confidence"] = classification.confidence
    result.metadata["reasoning"] = classification.reasoning

    return result
