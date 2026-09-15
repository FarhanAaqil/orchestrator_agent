"""
orchestrator_core/routes/route.py

POST /route — classify a user command to an agent.
Returns RouterResult (high confidence) or ClarificationNeeded (low confidence).
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

from orchestrator_core.core.router import classify
from orchestrator_core.models import RouterResult, ClarificationNeeded

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/route", tags=["Routing"])


class RouteRequest(BaseModel):
    command: str


@router.post("", response_model=None)
async def route_command(body: RouteRequest) -> RouterResult | ClarificationNeeded:
    """
    Classify a natural-language command and return the target agent.

    Returns RouterResult when confidence >= ROUTER_CONFIDENCE_THRESHOLD,
    or ClarificationNeeded when it is below.
    """
    logger.info("Routing command: %.80s", body.command)
    result = classify(body.command)
    logger.info("Route result: %s", result.model_dump())
    return result
