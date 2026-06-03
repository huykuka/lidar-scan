"""Auth router — login, current user, and user management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from .dependencies import get_current_user, roles_required
from .service import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserInfo,
    authenticate_user,
    create_access_token,
    create_user,
    delete_user,
    list_users,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login",
    description="Authenticate with username and password. Returns a JWT access token.",
)
async def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user)
    return LoginResponse(
        access_token=token,
        user=UserInfo(id=user.id, username=user.username, role=user.role),
    )


@router.get(
    "/me",
    response_model=UserInfo,
    summary="Current User",
    description="Get the currently authenticated user's profile.",
)
async def me(user: UserInfo = Depends(get_current_user)):
    return user


@router.get(
    "/users",
    response_model=list[UserInfo],
    summary="List Users",
    description="List all users. Admin only.",
)
@roles_required("admin")
async def get_users():
    users = list_users()
    return [UserInfo(**u) for u in users]


@router.post(
    "/users",
    response_model=UserInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Create User",
    description="Create a new user account. Admin only.",
)
@roles_required("admin")
async def create_new_user(req: RegisterRequest):
    try:
        user = create_user(req.username, req.password, req.role)
        return UserInfo(id=user.id, username=user.username, role=user.role)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{req.username}' already exists",
            )
        raise


@router.delete(
    "/users/{user_id}",
    summary="Delete User",
    description="Delete a user account. Admin only.",
)
@roles_required("admin")
async def remove_user(user_id: str, me: UserInfo = Depends(get_current_user)):
    if user_id == me.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    if not delete_user(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {"status": "deleted"}
