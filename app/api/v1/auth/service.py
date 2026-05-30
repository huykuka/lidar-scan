"""Authentication service — JWT token creation and password verification."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from pydantic import BaseModel

from app.db.models import UserModel
from app.db.session import SessionLocal

JWT_SECRET = os.getenv("JWT_SECRET", "lidar-standalone-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class UserInfo(BaseModel):
    id: str
    username: str
    role: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


def authenticate_user(username: str, password: str) -> Optional[UserModel]:
    """Verify username/password and return the user model if valid."""
    session = SessionLocal()
    try:
        user = (
            session.query(UserModel)
            .filter(UserModel.username == username)
            .first()
        )
        if user is None:
            return None
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return None
        # Detach from session before returning
        session.expunge(user)
        return user
    finally:
        session.close()


def create_access_token(user: UserModel) -> str:
    """Create a JWT access token for the given user."""
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.  Raises on invalid/expired."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def get_user_by_id(user_id: str) -> Optional[UserModel]:
    """Fetch a user by primary key."""
    session = SessionLocal()
    try:
        user = session.query(UserModel).filter(UserModel.id == user_id).first()
        if user:
            session.expunge(user)
        return user
    finally:
        session.close()


def create_user(username: str, password: str, role: str = "user") -> UserModel:
    """Create a new user account."""
    session = SessionLocal()
    try:
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = UserModel(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=pw_hash,
            role=role,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_users() -> list[dict]:
    """List all users (without password hashes)."""
    session = SessionLocal()
    try:
        users = session.query(UserModel).all()
        return [u.to_dict() for u in users]
    finally:
        session.close()


def delete_user(user_id: str) -> bool:
    """Delete a user by ID. Returns True if deleted."""
    session = SessionLocal()
    try:
        user = session.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            return False
        session.delete(user)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
