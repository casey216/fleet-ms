from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, UserRole, ActivityLog
from app.auth import require_user, require_role, get_password_hash, verify_password, has_permission

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def settings_home(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return templates.TemplateResponse("settings/settings.html", {
        "request": request,
        "user": current_user,
        "page": "settings",
        "is_admin": current_user.role == UserRole.admin,
    })


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse("settings/profile.html", {
        "request": request,
        "user": current_user,
        "page": "settings",
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
    })


@router.post("/profile")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    phone: str = Form(""),
    department: str = Form(""),
    timezone: str = Form("UTC"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # Check uniqueness (excluding self)
    existing_email = await db.execute(
        select(User).where(User.email == email, User.id != current_user.id)
    )
    if existing_email.scalar_one_or_none():
        return RedirectResponse(url="/settings/profile?error=Email+already+in+use", status_code=302)

    existing_username = await db.execute(
        select(User).where(User.username == username, User.id != current_user.id)
    )
    if existing_username.scalar_one_or_none():
        return RedirectResponse(url="/settings/profile?error=Username+already+taken", status_code=302)

    current_user.full_name = full_name
    current_user.email = email
    current_user.username = username
    current_user.phone = phone or None
    current_user.department = department or None
    current_user.timezone = timezone

    await db.commit()
    return RedirectResponse(url="/settings/profile?success=1", status_code=302)


@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(current_password, current_user.hashed_password):
        return RedirectResponse(url="/settings/profile?error=Current+password+is+incorrect", status_code=302)
    if new_password != confirm_password:
        return RedirectResponse(url="/settings/profile?error=New+passwords+do+not+match", status_code=302)
    if len(new_password) < 8:
        return RedirectResponse(url="/settings/profile?error=Password+must+be+at+least+8+characters", status_code=302)

    current_user.hashed_password = get_password_hash(new_password)
    await db.commit()
    return RedirectResponse(url="/settings/profile?success=Password+updated+successfully", status_code=302)


@router.get("/users", response_class=HTMLResponse)
async def user_management(
    request: Request,
    current_user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.full_name))
    users = result.scalars().all()

    return templates.TemplateResponse("settings/users.html", {
        "request": request,
        "user": current_user,
        "users": users,
        "roles": [r.value for r in UserRole],
        "page": "settings",
    })


@router.post("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    request: Request,
    role: str = Form(...),
    current_user: User = Depends(require_role(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404)

    target.role = role
    await db.commit()

    if request.headers.get("HX-Request"):
        role_colors = {
            "admin": "badge-error",
            "fleet_manager": "badge-warning",
            "driver": "badge-info",
            "viewer": "badge-ghost",
        }
        return HTMLResponse(
            f'<span class="badge {role_colors.get(role, "badge-ghost")}">{role.replace("_", " ").title()}</span>'
        )
    return RedirectResponse(url="/settings/users", status_code=302)