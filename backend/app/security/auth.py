"""JWT authentication and merchant authorization.

Demo mode intentionally keeps the seeded console frictionless. Outside demo
mode every protected route requires a signed access token and every
merchant-scoped operation checks the user's membership in that merchant.
"""

import uuid
from dataclasses import dataclass
from datetime import timezone,  datetime, timedelta
UTC = timezone.utc

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Role, User, UserMerchantRole
from app.security.passwords import verify_password

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID


def create_access_token(user_id: uuid.UUID, *, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expires = expires_minutes or settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "type": "access", "iat": now, "exp": now + timedelta(minutes=expires)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal | None:
    settings = get_settings()
    if credentials is None:
        if settings.DEMO_MODE:
            return None
        raise AppError("AUTHENTICATION_REQUIRED", "A bearer access token is required.", status_code=401)

    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "access" or not payload.get("sub"):
            raise ValueError("invalid token type")
        return Principal(user_id=uuid.UUID(payload["sub"]))
    except (JWTError, ValueError):
        raise AppError("INVALID_TOKEN", "The access token is invalid or expired.", status_code=401) from None


def get_current_user(
    principal: Principal | None = Depends(get_principal), db: Session = Depends(get_db),
) -> User:
    if principal is None:
        raise AppError("AUTHENTICATION_REQUIRED", "Sign in is required for this endpoint.", status_code=401)
    user = db.get(User, principal.user_id)
    if not user or not user.is_active:
        raise AppError("AUTHENTICATION_REQUIRED", "The account is inactive or no longer exists.", status_code=401)
    return user


def ensure_merchant_access(
    db: Session,
    merchant_id: uuid.UUID,
    principal: Principal | None,
    *,
    allowed_roles: set[str] | None = None,
) -> None:
    if principal is None:
        if get_settings().DEMO_MODE:
            return
        raise AppError("AUTHENTICATION_REQUIRED", "Sign in is required.", status_code=401)

    query = db.query(Role.name).join(
        UserMerchantRole, UserMerchantRole.role_id == Role.id,
    ).filter(
        UserMerchantRole.user_id == principal.user_id,
        UserMerchantRole.merchant_id == merchant_id,
    )
    role_name = query.scalar()
    if not role_name:
        raise AppError("MERCHANT_ACCESS_DENIED", "You do not have access to this merchant.", status_code=403)
    if allowed_roles and role_name not in allowed_roles:
        raise AppError("ROLE_NOT_ALLOWED", "Your role cannot perform this action.", status_code=403)


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.query(User).filter(User.email.ilike(email.strip())).one_or_none()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Email or password is incorrect.", status_code=401)
    return user