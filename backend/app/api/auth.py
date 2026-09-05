from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Merchant, Role, User, UserMerchantRole
from app.security.auth import authenticate_user, create_access_token, get_current_user
from app.security.passwords import hash_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=256)
    name: str = Field(min_length=2, max_length=255)
    merchant_name: str = Field(min_length=2, max_length=255)
    category: str = Field(min_length=2, max_length=255)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not any(char.islower() for char in value) or not any(char.isupper() for char in value):
            raise ValueError("Password must contain upper and lowercase letters.")
        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain a number.")
        return value


def _serialize_user(db: Session, user: User) -> dict:
    memberships = db.query(UserMerchantRole).filter(UserMerchantRole.user_id == user.id).all()
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "merchants": [{"merchant_id": str(item.merchant_id), "role_id": str(item.role_id)} for item in memberships],
    }


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.email, body.password)
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": _serialize_user(db, user),
    }


@router.post("/signup")
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.query(User).filter(User.email.ilike(email)).one_or_none():
        raise AppError("EMAIL_ALREADY_REGISTERED", "An account with this email already exists.", status_code=409)

    owner_role = db.query(Role).filter(Role.name == "OWNER").one_or_none()
    if not owner_role:
        owner_role = Role(name="OWNER")
        db.add(owner_role)
        db.flush()

    user = User(email=email, password_hash=hash_password(body.password), name=body.name.strip(), is_active=True)
    merchant = Merchant(name=body.merchant_name.strip(), category=body.category.strip(), status="active")
    db.add_all([user, merchant])
    db.flush()
    db.add(UserMerchantRole(user_id=user.id, merchant_id=merchant.id, role_id=owner_role.id))
    db.commit()
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": _serialize_user(db, user),
        "merchant_id": str(merchant.id),
    }


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _serialize_user(db, user)