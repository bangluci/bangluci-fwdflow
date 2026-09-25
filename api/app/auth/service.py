import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app.auth.models import INTERNAL_ROLES, LoginAttempt, Session, User
from app.envelope import AppError

_hasher = PasswordHasher()  # Argon2id
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

BAD_CREDENTIALS = "Email/SĐT hoặc mật khẩu không đúng"
THROTTLE_WINDOW = timedelta(minutes=15)
PAIR_FREE_FAILURES = 5
PAIR_MAX_DELAY = timedelta(minutes=15)
IP_MAX_FAILURES = 20
ABSOLUTE_SESSION_TTL = timedelta(days=30)
IDLE_INTERNAL = timedelta(hours=8)
IDLE_EXTERNAL = timedelta(days=7)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def normalize_identifier(identifier: str) -> str:
    value = identifier.strip().lower()
    if "@" in value:
        return value
    return "".join(ch for ch in value if ch.isdigit() or ch == "+")


def _pair_locked_until(db: DbSession, identifier: str, ip: str, now: datetime) -> datetime | None:
    """Từ lần sai thứ 5 của cặp (tài khoản, IP): trễ luỹ tiến 1s, 2s, 4s… tối đa 15 phút."""
    last_success = db.scalar(
        select(func.max(LoginAttempt.created_at)).where(
            LoginAttempt.identifier == identifier, LoginAttempt.ip == ip, LoginAttempt.succeeded.is_(True)
        )
    )
    since = max(filter(None, [last_success, now - timedelta(days=1)]))
    rows = db.execute(
        select(func.count(), func.max(LoginAttempt.created_at)).where(
            LoginAttempt.identifier == identifier,
            LoginAttempt.ip == ip,
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.created_at > since,
        )
    ).one()
    failures, last_failure = rows
    if failures < PAIR_FREE_FAILURES or last_failure is None:
        return None
    delay = min(timedelta(seconds=2 ** (failures - PAIR_FREE_FAILURES)), PAIR_MAX_DELAY)
    return last_failure + delay


def _ip_failures(db: DbSession, ip: str, now: datetime) -> int:
    return db.scalar(
        select(func.count()).where(
            LoginAttempt.ip == ip,
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.created_at > now - THROTTLE_WINDOW,
        )
    )


def _find_user(db: DbSession, identifier: str) -> User | None:
    column = User.email if "@" in identifier else User.phone
    return db.scalar(select(User).where(column == identifier))


def authenticate(db: DbSession, raw_identifier: str, password: str, ip: str) -> User:
    now = datetime.now(UTC)
    identifier = normalize_identifier(raw_identifier)
    locked_until = _pair_locked_until(db, identifier, ip, now)
    if (locked_until and locked_until > now) or _ip_failures(db, ip, now) >= IP_MAX_FAILURES:
        raise AppError("RATE_LIMITED", "Đăng nhập sai quá nhiều lần, vui lòng thử lại sau ít phút", 429)

    user = _find_user(db, identifier)
    # Luôn chạy hàm băm để thời gian xử lý như nhau dù tài khoản có tồn tại hay không.
    ok = verify_password(user.password_hash if user else _DUMMY_HASH, password)
    success = bool(user and ok and user.is_active)
    db.add(LoginAttempt(identifier=identifier, ip=ip, succeeded=success))
    if not success:
        db.commit()
        raise AppError("BAD_CREDENTIALS", BAD_CREDENTIALS, 401)
    return user


def clear_failed_attempts(db: DbSession, identifier: str) -> None:
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.identifier == normalize_identifier(identifier), LoginAttempt.succeeded.is_(False)
        )
    )


def _token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def create_session(db: DbSession, user: User, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)  # 256 bit
    db.add(
        Session(
            user_id=user.id,
            token_hash=_token_hash(token),
            absolute_expires_at=datetime.now(UTC) + ABSOLUTE_SESSION_TTL,
            ip=ip,
            user_agent=(user_agent or "")[:300],
        )
    )
    return token


def idle_timeout(role: str) -> timedelta:
    return IDLE_INTERNAL if role in INTERNAL_ROLES else IDLE_EXTERNAL


def resolve_session(db: DbSession, token: str) -> tuple[Session, User] | None:
    row = db.execute(
        select(Session, User).join(User, User.id == Session.user_id).where(Session.token_hash == _token_hash(token))
    ).first()
    if row is None:
        return None
    session, user = row
    now = datetime.now(UTC)
    expired = session.absolute_expires_at <= now or session.last_seen_at + idle_timeout(user.role) <= now
    if expired or not user.is_active:
        db.delete(session)
        db.commit()
        return None
    if now - session.last_seen_at > timedelta(minutes=1):
        session.last_seen_at = now
        db.commit()
    return session, user


def delete_session(db: DbSession, token: str) -> None:
    db.execute(delete(Session).where(Session.token_hash == _token_hash(token)))


def revoke_all_sessions(db: DbSession, user_id: int) -> None:
    db.execute(delete(Session).where(Session.user_id == user_id))
