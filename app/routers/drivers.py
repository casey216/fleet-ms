from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_db
from app.models import User, UserRole, Vehicle, ActivityLog
from app.auth import require_user, require_permission, get_password_hash, has_permission

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def drivers_list(
    request: Request,
    role: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if search:
        query = query.where(
            User.full_name.ilike(f"%{search}%") |
            User.email.ilike(f"%{search}%")
        )
    query = query.order_by(User.full_name)

    result = await db.execute(query)
    users = result.scalars().all()

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("drivers/driver_rows.html", {
            "request": request,
            "users": users,
            "user": current_user,
            "can_write": has_permission(current_user, "users", "write"),
        })

    return templates.TemplateResponse("drivers/drivers.html", {
        "request": request,
        "users": users,
        "user": current_user,
        "roles": [r.value for r in UserRole],
        "role_filter": role,
        "search": search,
        "page": "drivers",
        "can_write": has_permission(current_user, "users", "write"),
        "can_delete": has_permission(current_user, "users", "delete"),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_driver_form(
    request: Request,
    current_user: User = Depends(require_permission("users", "write")),
):
    return templates.TemplateResponse("drivers/driver_form.html", {
        "request": request,
        "user": current_user,
        "roles": [r.value for r in UserRole],
        "edit_user": None,
        "page": "drivers",
    })


@router.post("/new")
async def create_driver(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("driver"),
    phone: str = Form(""),
    department: str = Form(""),
    current_user: User = Depends(require_permission("users", "write")),
    db: AsyncSession = Depends(get_db),
):
    # Check uniqueness
    existing = await db.execute(select(User).where(
        (User.email == email) | (User.username == username)
    ))
    if existing.scalar_one_or_none():
        drivers_result = await db.execute(select(User))
        return templates.TemplateResponse("drivers/driver_form.html", {
            "request": request,
            "user": current_user,
            "roles": [r.value for r in UserRole],
            "edit_user": None,
            "error": "Email or username already exists",
            "page": "drivers",
        }, status_code=422)

    new_user = User(
        full_name=full_name,
        email=email,
        username=username,
        hashed_password=get_password_hash(password),
        role=role,
        phone=phone or None,
        department=department or None,
    )
    db.add(new_user)
    await db.commit()

    log = ActivityLog(user_id=current_user.id, action="create_user",
                      entity_type="user", entity_id=new_user.id)
    db.add(log)
    await db.commit()

    return RedirectResponse(url="/drivers", status_code=302)


@router.get("/{user_id}", response_class=HTMLResponse)
async def driver_detail(
    user_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404)

    # Get assigned vehicles
    vehicles = await db.execute(
        select(Vehicle).where(Vehicle.driver_id == user_id)
    )

    return templates.TemplateResponse("drivers/driver_detail.html", {
        "request": request,
        "target_user": target_user,
        "vehicles": vehicles.scalars().all(),
        "user": current_user,
        "page": "drivers",
        "can_write": has_permission(current_user, "users", "write"),
    })


@router.get("/{user_id}/edit", response_class=HTMLResponse)
async def edit_driver_form(
    user_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # Allow editing own profile OR admins editing others
    if current_user.id != user_id and not has_permission(current_user, "users", "write"):
        raise HTTPException(status_code=403)

    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse("drivers/driver_form.html", {
        "request": request,
        "user": current_user,
        "edit_user": target_user,
        "roles": [r.value for r in UserRole],
        "page": "drivers",
        "is_own_profile": current_user.id == user_id,
    })


@router.post("/{user_id}/edit")
async def update_driver(
    user_id: str,
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    role: str = Form("driver"),
    phone: str = Form(""),
    department: str = Form(""),
    is_active: bool = Form(True),
    new_password: str = Form(""),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.id != user_id and not has_permission(current_user, "users", "write"):
        raise HTTPException(status_code=403)

    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404)

    target_user.full_name = full_name
    target_user.email = email
    target_user.username = username
    target_user.phone = phone or None
    target_user.department = department or None

    # Only admins can change roles and active status
    if has_permission(current_user, "users", "write"):
        target_user.role = role
        target_user.is_active = is_active

    if new_password:
        target_user.hashed_password = get_password_hash(new_password)

    await db.commit()

    log = ActivityLog(user_id=current_user.id, action="update_user",
                      entity_type="user", entity_id=user_id)
    db.add(log)
    await db.commit()

    return RedirectResponse(url=f"/drivers/{user_id}", status_code=302)


@router.post("/{user_id}/toggle-active")
async def toggle_active(
    user_id: str,
    current_user: User = Depends(require_permission("users", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404)
    target_user.is_active = not target_user.is_active
    await db.commit()
    return HTMLResponse(
        f'<span class="badge {"badge-success" if target_user.is_active else "badge-error"}">'
        f'{"Active" if target_user.is_active else "Inactive"}</span>'
    )