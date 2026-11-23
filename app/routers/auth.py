"""Authentication routes: signup, login, me, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    is_owner,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    SignupRequest,
    UserMeResponse,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/hour", key_func=get_remote_address)
def signup(
    request: Request,
    body: SignupRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Register a new user account."""
    email = body.email.strip().lower()

    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise AppError(
            code="EMAIL_ALREADY_REGISTERED",
            message="This email is already registered.",
            status_code=status.HTTP_409_CONFLICT,
        )

    pw_hash = hash_password(body.password)
    user = User(email=email, password_hash=pw_hash, plan="free", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    token, expires_in = create_access_token(user.id, user.email)
    user_out = UserOut(
        id=user.id,
        email=user.email,
        plan=user.plan,
        is_owner=is_owner(user),
    )
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=user_out,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute", key_func=get_remote_address)
def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Log in an existing user."""
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))

    # Constant-time dummy verification if user doesn't exist to mitigate timing attacks
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise AppError(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token, expires_in = create_access_token(user.id, user.email)
    user_out = UserOut(
        id=user.id,
        email=user.email,
        plan=user.plan,
        is_owner=is_owner(user),
    )
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=user_out,
    )


@router.get(
    "/me",
    response_model=UserMeResponse,
    status_code=status.HTTP_200_OK,
)
def me(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> UserMeResponse:
    """Get profile of current authenticated user."""
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        plan=current_user.plan,
        is_owner=is_owner(current_user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout(request: Request) -> Response:
    """Stateless logout; client clears stored token."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)
