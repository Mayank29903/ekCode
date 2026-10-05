import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, get_db
from .models import ApiKey, User

ph = PasswordHasher()
COOKIE = "ek_session"
# Checked when the email is unknown, so "no such user" costs the same time as "wrong password".
_DUMMY_HASH = ph.hash(secrets.token_hex(16))


def hash_password(p: str) -> str:
    return ph.hash(p)


def verify_password(h: str, p: str) -> bool:
    try:
        return ph.verify(h, p)
    except (VerificationError, InvalidHashError):
        return False


def burn_verify(p: str) -> None:
    verify_password(_DUMMY_HASH, p)


def session_version(user: User) -> str:
    """Changes whenever the password changes, which invalidates every session issued before (ASVS 3.3)."""
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:16]


def set_session(resp: Response, user: User) -> None:
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user.id), "role": user.role, "pv": session_version(user), "iat": now,
              "exp": now + timedelta(minutes=settings.jwt_ttl_minutes)}
    token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    resp.set_cookie(COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="lax",
                    max_age=settings.jwt_ttl_minutes * 60, path="/")


def clear_session(resp: Response) -> None:
    resp.delete_cookie(COOKIE, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    """(raw key shown once, display prefix, hash stored in the DB)"""
    raw = "ek_" + secrets.token_urlsafe(32)
    return raw, raw[:10], hash_api_key(raw)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    if key := request.headers.get("x-api-key"):
        if not db.query(ApiKey.id).filter_by(key_hash=hash_api_key(key)).first():
            raise HTTPException(401, "Invalid API key")
        # Machine clients (ERP pulls, BI tools) are read-only: the auditor role can read and export, never change.
        # The object is never added to a session.
        return User(id=None, email="api-key", name="API client", role="auditor", password_hash="")
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not signed in")
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        user_id = uuid.UUID(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(401, "Session expired") from None
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")
    if data.get("pv") != session_version(user):
        raise HTTPException(401, "Session expired: the password was changed")
    return user


def authenticate(request: Request) -> User:
    """current_user without holding a pooled DB connection, for long-lived responses such as SSE streams."""
    with SessionLocal() as db:
        return current_user(request, db)


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission for this action")
        return user
    return dep


STEWARD = ("admin", "data_steward")
ANY = ("admin", "data_steward", "cpse_user", "auditor")
