from fastapi import Header, HTTPException, status

from .config import settings


def require_token(authorization: str = Header(default="")) -> str:
    """Bearer auth. NOTE: single shared static token, no per-tenant scoping."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.api_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid token")
    return token
