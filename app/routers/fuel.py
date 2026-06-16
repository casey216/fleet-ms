from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import date

from app.database import get_db
from app.models import FuelLog, Vehicle, User, ActivityLog
from app.auth import require_user, require_permission, has_permission

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def fuel_list(
    request: Request,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(FuelLog, Vehicle).join(Vehicle, FuelLog.vehicle_id == Vehicle.id)
    if vehicle_id:
        query = query.where(FuelLog.vehicle_id == vehicle_id)
    query = query.order_by(FuelLog.date.desc()).limit(100)

    result = await db.execute(query)
    fuel_logs = result.all()

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    total_cost = await db.scalar(select(func.sum(FuelLog.total_cost))) or 0
    total_liters = await db.scalar(select(func.sum(FuelLog.liters))) or 0

    return request.app.state.templates.TemplateResponse("fuel/fuel.html", {
        "request": request,
        "fuel_logs": fuel_logs,
        "vehicles": vehicles.scalars().all(),
        "vehicle_filter": vehicle_id,
        "total_cost": float(total_cost),
        "total_liters": float(total_liters),
        "user": current_user,
        "page": "fuel",
        "can_write": has_permission(current_user, "fuel", "write"),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_fuel_form(
    request: Request,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_permission("fuel", "write")),
    db: AsyncSession = Depends(get_db),
):
    vehicles = await db.execute(select(Vehicle).where(Vehicle.status == "active"))
    return request.app.state.templates.TemplateResponse("fuel/fuel_form.html", {
        "request": request,
        "user": current_user,
        "vehicles": vehicles.scalars().all(),
        "selected_vehicle": vehicle_id,
        "log": None,
        "today": date.today().isoformat(),
        "page": "fuel",
    })


@router.post("/new")
async def create_fuel_log(
    request: Request,
    vehicle_id: str = Form(...),
    log_date: str = Form(...),
    liters: float = Form(...),
    cost_per_liter: float = Form(...),
    odometer: int = Form(...),
    station: str = Form(""),
    full_tank: bool = Form(True),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("fuel", "write")),
    db: AsyncSession = Depends(get_db),
):
    total_cost = liters * cost_per_liter
    log = FuelLog(
        vehicle_id=vehicle_id,
        logged_by=current_user.id,
        date=date.fromisoformat(log_date),
        liters=liters,
        cost_per_liter=cost_per_liter,
        total_cost=total_cost,
        odometer=odometer,
        station=station or None,
        full_tank=full_tank,
        notes=notes or None,
    )
    db.add(log)

    # Update vehicle odometer
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if vehicle and odometer > vehicle.odometer:
        vehicle.odometer = odometer

    activity = ActivityLog(user_id=current_user.id, action="add_fuel_log",
                           entity_type="fuel_log", entity_id=log.id)
    db.add(activity)
    await db.commit()

    return RedirectResponse(url="/fuel", status_code=302)


@router.post("/{log_id}/delete")
async def delete_fuel_log(
    log_id: str,
    current_user: User = Depends(require_permission("fuel", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FuelLog).where(FuelLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404)
    await db.delete(log)
    await db.commit()
    return RedirectResponse(url="/fuel", status_code=302)