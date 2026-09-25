from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.audit.service import record_audit, snapshot
from app.auth.deps import current_user, require
from app.auth.models import Role, User
from app.auth.service import (
    ABSOLUTE_SESSION_TTL,
    authenticate,
    clear_failed_attempts,
    create_session,
    delete_session,
    hash_password,
    normalize_identifier,
    revoke_all_sessions,
)
from app.config import get_settings
from app.db import get_db
from app.envelope import AppError, ok
from app.ratelimit import client_ip

router = APIRouter()
USER_FIELDS = ("email", "phone", "full_name", "role", "customer_id", "driver_id", "is_active")


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def user_out(user: User) -> dict:
    return {"id": user.id, **{f: getattr(user, f) for f in USER_FIELDS}}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: DbSession = Depends(get_db)) -> dict:
    ip = client_ip(request)
    user = authenticate(db, body.identifier, body.password, ip)
    token = create_session(db, user, ip, request.headers.get("user-agent"))
    record_audit(db, user.id, "LOGIN", "login", user.id, after={"identifier": body.identifier, "result": "ok"},
                 ip=ip)
    db.commit()
    response.set_cookie(
        get_settings().session_cookie_name,
        token,
        max_age=int(ABSOLUTE_SESSION_TTL.total_seconds()),
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return ok(user_out(user))


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)) -> dict:
    name = get_settings().session_cookie_name
    token = request.cookies.get(name)
    if token:
        delete_session(db, token)
        db.commit()
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")
    return ok()


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    return ok(user_out(user))


class UserCreate(BaseModel):
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    full_name: str = Field(min_length=1, max_length=200)
    role: Role
    customer_id: int | None = None
    driver_id: int | None = None
    password: str = Field(min_length=8, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> "UserCreate":
        if not self.email and not self.phone:
            raise ValueError("Cần email hoặc số điện thoại")
        if self.role == Role.CUSTOMER and not self.customer_id:
            raise ValueError("Tài khoản khách hàng cần customer_id")
        if self.role == Role.DRIVER and not self.driver_id:
            raise ValueError("Tài khoản tài xế cần driver_id")
        return self


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: Role | None = None
    is_active: bool | None = None
    customer_id: int | None = None
    driver_id: int | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=200)


def _get_user(db: DbSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError("NOT_FOUND", "Không tìm thấy người dùng", 404)
    return user


@router.get("/users")
def list_users(q: str | None = None, db: DbSession = Depends(get_db),
               _: User = Depends(require("users.manage"))) -> dict:
    stmt = select(User).order_by(User.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.phone.ilike(like), User.full_name.ilike(like)))
    return ok([user_out(u) for u in db.scalars(stmt.limit(500))])


@router.post("/users", status_code=201)
def create_user(body: UserCreate, request: Request, db: DbSession = Depends(get_db),
                admin: User = Depends(require("users.manage"))) -> dict:
    user = User(
        email=normalize_identifier(body.email) if body.email else None,
        phone=normalize_identifier(body.phone) if body.phone else None,
        full_name=body.full_name,
        role=body.role.value,
        customer_id=body.customer_id,
        driver_id=body.driver_id,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("CONFLICT", "Email hoặc số điện thoại đã được dùng, hoặc liên kết không hợp lệ", 409) from exc
    record_audit(db, admin.id, "CREATE", "user", user.id, after=snapshot(user, USER_FIELDS), ip=client_ip(request))
    db.commit()
    return ok(user_out(user))


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, db: DbSession = Depends(get_db),
                admin: User = Depends(require("users.manage"))) -> dict:
    user = _get_user(db, user_id)
    before = snapshot(user, USER_FIELDS)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(user, key, value.value if isinstance(value, Role) else value)
    if user.role == Role.CUSTOMER and not user.customer_id or user.role == Role.DRIVER and not user.driver_id:
        raise AppError("VALIDATION_ERROR", "Vai trò này cần liên kết khách hàng / tài xế", 422)
    if "role" in changes or changes.get("is_active") is False:
        revoke_all_sessions(db, user.id)
    record_audit(db, admin.id, "UPDATE", "user", user.id, before=before, after=snapshot(user, USER_FIELDS),
                 ip=client_ip(request))
    db.commit()
    return ok(user_out(user))


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, body: PasswordReset, request: Request, db: DbSession = Depends(get_db),
                   admin: User = Depends(require("users.manage"))) -> dict:
    user = _get_user(db, user_id)
    user.password_hash = hash_password(body.password)
    revoke_all_sessions(db, user.id)
    record_audit(db, admin.id, "RESET_PASSWORD", "user", user.id,
                 before={"password_hash": "old"}, after={"password_hash": "new"}, ip=client_ip(request))
    db.commit()
    return ok()


@router.post("/users/{user_id}/unlock")
def unlock_user(user_id: int, request: Request, db: DbSession = Depends(get_db),
                admin: User = Depends(require("users.manage"))) -> dict:
    user = _get_user(db, user_id)
    for identifier in filter(None, [user.email, user.phone]):
        clear_failed_attempts(db, identifier)
    record_audit(db, admin.id, "UNLOCK", "user", user.id, ip=client_ip(request))
    db.commit()
    return ok()
