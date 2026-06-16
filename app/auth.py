from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database import get_db
from app.models import User, UserRole

pwd_context = PasswordHash.recommended()

ROLE_PERMISSIONS = {
    UserRole.admin: {
        "users": ["read", "write", "delete"],
        "vehicles": ["read", "write", "delete"],
        "contracts": ["read", "write", "delete"],
        "insurance": ["read", "write", "delete"],
        "fuel": ["read", "write", "delete"],
        "maintenance": ["read", "write", "delete"],
        "reports": ["read"],
        "settings": ["read", "write"],
        "alerts": ["read", "write", "delete"],
    },
    UserRole.fleet_manager: {
        "users": ["read"],
        "vehicles": ["read", "write"],
        "contracts": ["read", "write"],
        "insurance": ["read", "write"],
        "fuel": ["read", "write"],
        "maintenance": ["read", "write"],
        "reports": ["read"],
        "settings": ["read"],
        "alerts": ["read", "write"],
    },
    UserRole.driver: {
        "vehicles": ["read"],
        "contracts": ["read"],
        "insurance": ["read"],
        "fuel": ["read", "write"],
        "maintenance": ["read"],
        "reports": [],
        "settings": [],
        "alerts": ["read"],
    },
    UserRole.viewer: {
        "vehicles": ["read"],
        "contracts": ["read"],
        "insurance": ["read"],
        "fuel": ["read"],
        "maintenance": ["read"],
        "reports": ["read"],
        "settings": [],
        "alerts": ["read"],
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    return result.scalar_one_or_none()


async def require_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/auth/login"}
        )
    return user


def require_role(*roles: UserRole):
    async def checker(request: Request, db: AsyncSession = Depends(get_db)) -> User:
        user = await get_current_user(request, db)
        if not user:
            raise HTTPException(status_code=302, headers={"Location": "/auth/login"})
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


def has_permission(user: User, resource: str, action: str) -> bool:
    perms = ROLE_PERMISSIONS.get(UserRole(user.role), {})
    return action in perms.get(resource, [])


def require_permission(resource: str, action: str):
    async def checker(request: Request, db: AsyncSession = Depends(get_db)) -> User:
        user = await get_current_user(request, db)
        if not user:
            raise HTTPException(status_code=302, headers={"Location": "/auth/login"})
        if not has_permission(user, resource, action):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker