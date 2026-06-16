from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.dependencies import get_template
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Annotated
from datetime import date

from app.database import get_db
from app.models import OdometerLog, Vehicle, User, ActivityLog
from app.auth import require_user, require_permission, has_permission


TempDeps = Annotated[Jinja2Templates, Depends(get_template)]

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def odometer_list(
    request: Request,
    templates: TempDeps,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(OdometerLog, Vehicle)
        .join(Vehicle, OdometerLog.vehicle_id == Vehicle.id)
        .order_by(OdometerLog.date.desc(), OdometerLog.created_at.desc())
    )
    if vehicle_id:
        query = query.where(OdometerLog.vehicle_id == vehicle_id)

    result = await db.execute(query)
    logs = result.all()

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))

    # Compute distance between consecutive readings per vehicle
    enriched = []
    prev_by_vehicle: dict[str, int] = {}
    # Process in chronological order for delta
    for log, vehicle in reversed(logs):
        prev = prev_by_vehicle.get(log.vehicle_id)
        delta = log.value - prev if prev is not None else None
        prev_by_vehicle[log.vehicle_id] = log.value
        enriched.append((log, vehicle, delta))
    enriched.reverse()

    return templates.TemplateResponse("odometer/odometer.html", {
        "request": request,
        "logs": enriched,
        "vehicles": vehicles.scalars().all(),
        "vehicle_filter": vehicle_id,
        "user": current_user,
        "page": "odometer",
        "can_write": has_permission(current_user, "vehicles", "write"),
        "today": date.today(),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_odometer_form(
    request: Request,
    templates: TempDeps,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))

    # Pre-fill current odometer if vehicle selected
    current_odometer = None
    if vehicle_id:
        veh = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
        v = veh.scalar_one_or_none()
        if v:
            current_odometer = v.odometer

    return templates.TemplateResponse("odometer/odometer_form.html", {
        "request": request,
        "user": current_user,
        "vehicles": vehicles.scalars().all(),
        "log": None,
        "selected_vehicle": vehicle_id,
        "current_odometer": current_odometer,
        "today": date.today().isoformat(),
        "page": "odometer",
    })


@router.post("/new")
async def create_odometer_log(
    request: Request,
    vehicle_id: str = Form(...),
    log_date: str = Form(...),
    value: int = Form(...),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    # Validate the vehicle actually exists before creating an orphaned log
    veh = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = veh.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    is_regression = value < vehicle.odometer

    log = OdometerLog(
        vehicle_id=vehicle_id,
        date=date.fromisoformat(log_date),
        value=value,
        notes=notes or None,
    )
    db.add(log)
    await db.flush()  # ensures log.id is populated before we reference it below

    # Update vehicle's odometer only if this reading is higher (never go backwards)
    if value > vehicle.odometer:
        vehicle.odometer = value

    activity = ActivityLog(
        user_id=current_user.id,
        action="add_odometer_log",
        entity_type="odometer_log",
        entity_id=log.id,
        details={
            "vehicle_id": vehicle_id,
            "license_plate": vehicle.license_plate,
            "value": value,
            "previous_odometer": vehicle.odometer if not is_regression else None,
            "flagged_regression": is_regression,
        },
    )
    db.add(activity)
    await db.commit()

    if is_regression and request.headers.get("HX-Request"):
        return HTMLResponse(
            '<div class="flash flash-warning">Reading saved, but it is lower than the '
            'vehicle\'s current odometer — the vehicle record was not updated.</div>'
        )

    redirect_url = "/odometer"
    if is_regression:
        redirect_url += "?warning=Reading+lower+than+current+odometer+%E2%80%94+vehicle+not+updated"
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/{log_id}/edit", response_class=HTMLResponse)
async def edit_odometer_form(
    log_id: str,
    templates: TempDeps,
    request: Request,
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OdometerLog).where(OdometerLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404)

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    return templates.TemplateResponse("odometer/odometer_form.html", {
        "request": request,
        "user": current_user,
        "log": log,
        "vehicles": vehicles.scalars().all(),
        "today": date.today().isoformat(),
        "page": "odometer",
    })


@router.post("/{log_id}/edit")
async def update_odometer_log(
    log_id: str,
    vehicle_id: str = Form(...),
    log_date: str = Form(...),
    value: int = Form(...),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OdometerLog).where(OdometerLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404)

    # Validate the (possibly re-assigned) vehicle exists
    veh = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = veh.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    old_value = log.value
    old_vehicle_id = log.vehicle_id

    log.vehicle_id = vehicle_id
    log.date = date.fromisoformat(log_date)
    log.value = value
    log.notes = notes or None

    activity = ActivityLog(
        user_id=current_user.id,
        action="update_odometer_log",
        entity_type="odometer_log",
        entity_id=log_id,
        details={
            "vehicle_id": vehicle_id,
            "license_plate": vehicle.license_plate,
            "old_value": old_value,
            "new_value": value,
            "vehicle_reassigned": old_vehicle_id != vehicle_id,
        },
    )
    db.add(activity)
    await db.commit()
    return RedirectResponse(url="/odometer", status_code=302)


@router.post("/{log_id}/delete")
async def delete_odometer_log(
    log_id: str,
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OdometerLog).where(OdometerLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404)

    veh = await db.execute(select(Vehicle).where(Vehicle.id == log.vehicle_id))
    vehicle = veh.scalar_one_or_none()

    activity = ActivityLog(
        user_id=current_user.id,
        action="delete_odometer_log",
        entity_type="odometer_log",
        entity_id=log_id,
        details={
            "vehicle_id": log.vehicle_id,
            "license_plate": vehicle.license_plate if vehicle else None,
            "value": log.value,
            "date": log.date.isoformat() if log.date else None,
        },
    )
    db.add(activity)
    await db.delete(log)
    await db.commit()
    return RedirectResponse(url="/odometer", status_code=302)