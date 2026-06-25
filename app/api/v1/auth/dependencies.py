"""FastAPI dependencies for authentication and authorization.

Role hierarchy (highest to lowest): service > admin > user

Usage — decorator style (like NestJS @Roles()):

    @router.get("/path")
    @roles_required("admin")          # admin + service allowed
    async def handler():
        ...

    @router.get("/other")
    @roles_required("service")        # service only
    async def other():
        ...

If the handler needs the authenticated user object, combine with
``get_current_user``:

    @router.delete("/users/{uid}")
    @roles_required("admin")
    async def delete(uid: str, me: UserInfo = Depends(get_current_user)):
        ...
"""

from __future__ import annotations

import inspect
from functools import wraps

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .service import UserInfo, decode_access_token, get_user_by_id

_bearer_scheme = HTTPBearer(auto_error=False)

ROLE_LEVELS: dict[str, int] = {"user": 0, "admin": 1, "service": 2}


async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UserInfo:
    """Extract and validate the JWT from the Authorization header."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(payload["sub"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return UserInfo(id=user.id, username=user.username, role=user.role)


# ---------------------------------------------------------------------------
# @roles_required decorator  (NestJS-style Guard)
# ---------------------------------------------------------------------------

def _make_role_guard(min_role: str) -> object:
    """Build a FastAPI dependency that enforces a minimum role level."""
    required_level = ROLE_LEVELS[min_role]
    label = f"{min_role.capitalize()} access required"

    async def _guard(
            credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> UserInfo:
        user = await get_current_user(credentials)
        if ROLE_LEVELS.get(user.role, 0) < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=label,
            )
        return user

    return _guard


def roles_required(*allowed_roles: str):
    """Decorator that restricts an endpoint to users with a minimum role.

    The *highest* role in ``allowed_roles`` determines the minimum level.
    E.g. ``@roles_required("admin")`` allows admin **and** service.

    Apply **below** the ``@router`` decorator::

        @router.post("/reload")
        @roles_required("admin")
        async def reload():
            ...
    """
    if not allowed_roles:
        raise ValueError("roles_required() needs at least one role")
    for r in allowed_roles:
        if r not in ROLE_LEVELS:
            raise ValueError(f"Unknown role: {r!r}")

    min_role = max(allowed_roles, key=lambda r: ROLE_LEVELS[r])
    guard = _make_role_guard(min_role)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            kwargs.pop("_role_guard", None)
            return await func(*args, **kwargs)

        sig = inspect.signature(func)
        guard_param = inspect.Parameter(
            "_role_guard",
            inspect.Parameter.KEYWORD_ONLY,
            default=Depends(guard),
            annotation=UserInfo,
        )
        wrapper.__signature__ = sig.replace(
            parameters=[*sig.parameters.values(), guard_param]
        )
        return wrapper

    return decorator
