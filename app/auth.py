"""Verify Supabase-issued JWTs.

Supabase signs access tokens with an asymmetric key (ES256 on this project),
so the API only ever needs the PUBLIC half, fetched from the project's JWKS
endpoint. There is no shared auth secret in this codebase and none belongs
in one -- a leaked HS256 secret lets anyone mint tokens for any user.

The flow:
    browser  -- supabase.auth.signInWithPassword() --> Supabase Auth
    browser  <-- access_token (JWT, ES256) ----------- Supabase Auth
    browser  -- Authorization: Bearer <jwt> ---------> this API
    this API -- verify signature against JWKS -------> user id from claims
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

from common.config import (
    SUPABASE_JWKS_URL,
    SUPABASE_JWT_AUDIENCE,
    SUPABASE_JWT_ISSUER,
)

# Supabase may sign with EC or RSA depending on when the key was created.
# Listing both means a key rotation to a different family keeps working.
# Never add "HS256" here: with a symmetric algorithm an attacker who knows
# the public key could sign their own tokens.
_ALGORITHMS = ["ES256", "RS256"]

_jwk_client: PyJWKClient | None = None


def _client() -> PyJWKClient:
    """Lazily built so importing this module never does network I/O.

    lifespan is 5 minutes because Supabase's edge caches the JWKS for 10;
    caching longer than that on our side would keep serving a retired key
    after a rotation.
    """
    global _jwk_client
    if SUPABASE_JWKS_URL is None:
        raise HTTPException(
            status_code=503,
            detail="auth not configured: no Supabase project in DATABASE_URL",
        )
    if _jwk_client is None:
        _jwk_client = PyJWKClient(SUPABASE_JWKS_URL, cache_keys=True, lifespan=300)
    return _jwk_client


def _bearer_token(request: Request) -> str | None:
    """The token from `Authorization: Bearer <jwt>`, or None."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _verify(token: str) -> dict:
    """Decoded claims, or raise 401.

    get_signing_key_from_jwt matches the token's `kid` header against the
    JWKS, which is what makes rotation transparent. Audience and issuer are
    checked too: a signature-only check would accept a valid token minted by
    a *different* Supabase project.
    """
    try:
        signing_key = _client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            audience=SUPABASE_JWT_AUDIENCE,
            issuer=SUPABASE_JWT_ISSUER,
        )
    except jwt.PyJWTError as exc:
        # The reason is deliberately echoed: these are all client-side
        # mistakes (expired, wrong project, malformed), never secrets.
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from None


def current_user(request: Request) -> dict:
    """FastAPI dependency for endpoints that REQUIRE a logged-in user.

        @app.get("/api/favorites")
        def favorites(user: dict = Depends(current_user)): ...

    Returns the JWT claims; `sub` is the Supabase user id (a uuid) and is
    what foreign keys should reference.
    """
    token = _bearer_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return _verify(token)


def optional_user(request: Request) -> dict | None:
    """Same, but None instead of 401 when signed out.

    For pages that personalise when they can and still work when they
    cannot -- the feed being the obvious one, since logged-out visitors are
    meant to see trending rather than a login wall.
    """
    token = _bearer_token(request)
    if token is None:
        return None
    return _verify(token)
