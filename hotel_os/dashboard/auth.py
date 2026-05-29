# ============================================================
# HotelOS — Dashboard Authentication
#
# Simple token-based auth:
#   POST /auth/login  → returns JWT-like token
#   All other dashboard routes require Bearer token in header
#   WebSocket connections require ?token=<token> query param
# ============================================================

import time
import hmac
import hashlib
import base64
import json
import logging

from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from shared.config import DASHBOARD_SECRET_KEY, DASHBOARD_USERNAME, DASHBOARD_PASSWORD, TOKEN_EXPIRE_MINUTES

logger = logging.getLogger("hotelos.dashboard.auth")

security = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------
# Simple token: base64(payload) + "." + HMAC signature
# ------------------------------------------------------------------

def _sign(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig  = hmac.new(
        DASHBOARD_SECRET_KEY.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{body}.{sig}"


def _verify(token: str) -> dict | None:
    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(
            DASHBOARD_SECRET_KEY.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": time.time() + TOKEN_EXPIRE_MINUTES * 60,
        "iat": time.time(),
    }
    return _sign(payload)


def verify_token(token: str) -> dict:
    payload = _verify(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
        )
    return payload


# ------------------------------------------------------------------
# FastAPI dependency
# ------------------------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Bearer token.",
        )
    return verify_token(credentials.credentials)


# ------------------------------------------------------------------
# Pydantic schema
# ------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


def authenticate(username: str, password: str) -> str:
    """Verify credentials and return token, or raise 401."""
    if username != DASHBOARD_USERNAME or password != DASHBOARD_PASSWORD:
        logger.warning("Failed login attempt for user '%s'", username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
        )
    token = create_token(username)
    logger.info("User '%s' logged in successfully", username)
    return token
