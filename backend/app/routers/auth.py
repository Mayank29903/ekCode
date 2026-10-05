import time
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..db import get_db
from ..models import Cpse, User
from ..security import burn_verify, clear_session, current_user, hash_password, set_session, verify_password

router = APIRouter(tags=["auth"])

# Failed-attempt throttle (OWASP ASVS 2.2.1), per client IP + account, in process memory.
_WINDOW_S, _MAX_FAILS, _MAX_KEYS = 15 * 60, 10, 10_000
_fails: dict[str, list[float]] = {}


class LoginIn(BaseModel):
    # Plain str, not EmailStr: email-validator rejects special-use domains such as the seeded admin@ekcode.local.
    email: str = Field(min_length=3, max_length=200, pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    password: str = Field(min_length=8, max_length=200)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$", v):
            raise ValueError('Password must contain at least one letter, one number, and one special character')
        return v

class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    password: str = Field(min_length=8, max_length=200)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$", v):
            raise ValueError('Password must contain at least one letter, one number, and one special character')
        return v


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


def user_out(db: Session, u: User) -> dict:
    cpse = db.get(Cpse, u.cpse_id) if u.cpse_id else None
    return {"id": str(u.id), "email": u.email, "name": u.name, "role": u.role, "cpse": cpse.code if cpse else None}


def _recent_fails(key: str) -> list[float]:
    now = time.monotonic()
    recent = [t for t in _fails.get(key, []) if now - t < _WINDOW_S]
    if recent:
        _fails[key] = recent
    else:
        _fails.pop(key, None)
    return recent


def _record_fail(key: str) -> None:
    if len(_fails) >= _MAX_KEYS:                       # spraying many accounts must not grow memory without bound
        for k in list(_fails):
            _recent_fails(k)
    _fails.setdefault(key, []).append(time.monotonic())


def _client(request: Request) -> str:
    return request.client.host if request.client else "-"


@router.post("/auth/login")
def login(body: LoginIn, request: Request, resp: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    key = f"login|{_client(request)}|{email}"
    if len(_recent_fails(key)) >= _MAX_FAILS:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    u = db.query(User).filter(User.email == email).first()
    if u is None:
        burn_verify(body.password)
    if not u or not verify_password(u.password_hash, body.password):
        _record_fail(key)
        raise HTTPException(401, "Wrong email or password")
    _fails.pop(key, None)
    set_session(resp, u)
    return user_out(db, u)


@router.post("/auth/register")
def register(body: RegisterIn, request: Request, resp: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "User with this email already exists")

    new_user = User(
        email=email,
        name=body.name,
        password_hash=hash_password(body.password),
        role="cpse_user" 
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    set_session(resp, new_user)
    return user_out(db, new_user)


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_out(db, user)


@router.post("/auth/password")
def change_password(body: PasswordIn, request: Request, resp: Response, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    """Change your own password. Every other session of this user stops working (ASVS 2.1, 3.3)."""
    if user.id is None:
        raise HTTPException(403, "API keys cannot change passwords")
    key = f"password|{_client(request)}|{user.id}"
    if len(_recent_fails(key)) >= _MAX_FAILS:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    if not verify_password(user.password_hash, body.current_password):
        _record_fail(key)
        raise HTTPException(400, "The current password is not correct")
    if body.new_password == body.current_password:
        raise HTTPException(422, "Choose a password different from the current one")
    if body.new_password.strip().lower() == user.email.lower():
        raise HTTPException(422, "The password must not be your email address")
    user.password_hash = hash_password(body.new_password)
    write_audit(db, user, "password", "user", user.id, None, {"password": "changed by the user"})
    db.commit()
    _fails.pop(key, None)
    set_session(resp, user)                            # this browser stays signed in with a fresh token
    return {"ok": True}


@router.post("/auth/logout")
def logout(resp: Response):
    clear_session(resp)
    return {"ok": True}


@router.get("/cpses")
def cpses(db: Session = Depends(get_db), _=Depends(current_user)):
    return [{"code": c.code, "name": c.name, "sector": c.sector} for c in db.query(Cpse).order_by(Cpse.code)]
