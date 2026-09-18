"""
orchestrator_core/dependencies.py

Security and authentication dependencies for FastAPI routes.
Enforces Bearer token verification against environment configuration.
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from orchestrator_core.config import Settings, get_settings

security = HTTPBearer(auto_error=False)


def verify_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    settings: Settings = Depends(get_settings),
) -> Optional[str]:
    """
    Validate incoming HTTP Bearer token against settings.auth_token.

    Contract:
      - If settings.auth_token is None or empty (e.g. unconfigured local dev/test environment),
        authentication is bypassed to allow unauthenticated development.
      - If settings.auth_token is configured (production / staging / secured deployment),
        a valid matching Authorization: Bearer <token> header is strictly required.
        Missing or mismatching credentials raise 401 Unauthorized.
    """
    expected_token = settings.auth_token
    if not expected_token:
        return None

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(credentials.credentials, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials
