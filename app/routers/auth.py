from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.database import get_db
from app.models import User, UserRole, ActivityLog
from app.auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, require_user
)
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("auth/login.html", {
        "request": request,
        "app_name": settings.APP_NAME,
    })


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Invalid email or password",
            "email": email,
            "app_name": settings.APP_NAME,
        }, status_code=401)

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    # Log activity
    log = ActivityLog(
        user_id=user.id,
        action="login",
        entity_type="user",
        entity_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)
    await db.commit()

    token = create_access_token({"sub": user.id, "role": user.role.value})
    response = RedirectResponse(url="/dashboard", status_code=302)
    max_age = 60 * 60 * 24 * 30 if remember else None
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        max_age=max_age,
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {
        "request": request,
        "app_name": settings.APP_NAME,
    })


@router.post("/register")
async def register(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    errors = {}

    if password != confirm_password:
        errors["password"] = "Passwords do not match"

    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        errors["email"] = "Email already registered"

    # Check username uniqueness
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        errors["username"] = "Username already taken"

    if errors:
        return templates.TemplateResponse("auth/register.html", {
            "request": request,
            "errors": errors,
            "form": {"full_name": full_name, "email": email, "username": username},
            "app_name": settings.APP_NAME,
        }, status_code=422)

    # Check if first user (make admin)
    result = await db.execute(select(User))
    is_first = result.first() is None

    user = User(
        full_name=full_name,
        email=email,
        username=username,
        hashed_password=get_password_hash(password),
        role=UserRole.admin if is_first else UserRole.viewer,
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": user.id, "role": user.role.value})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return response