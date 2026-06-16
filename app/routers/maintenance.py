from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Annotated
from datetime import date

from app.database import get_db
from app.models import MaintenanceRecord, MaintenanceStatus, MaintenanceType, Vehicle, User, ActivityLog
from app.auth import require_user, require_permission, has_permission
from app.dependencies import get_template


TempDeps = Annotated[Jinja2Templates, Depends(get_template)]

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def maintenance_list(
    request: Request,
    templates: TempDeps,
    status: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(MaintenanceRecord, Vehicle).join(Vehicle, MaintenanceRecord.vehicle_id == Vehicle.id)
    if status:
        query = query.where(MaintenanceRecord.status == status)
    if vehicle_id:
        query = query.where(MaintenanceRecord.vehicle_id == vehicle_id)
    query = query.order_by(MaintenanceRecord.scheduled_date.desc())

    result = await db.execute(query)
    records = result.all()

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("maintenance/maintenance_rows.html", {
            "request": request,
            "records": records,
            "user": current_user,
            "can_write": has_permission(current_user, "maintenance", "write"),
        })

    return templates.TemplateResponse("maintenance/maintenance.html", {
        "request": request,
        "records": records,
        "vehicles": vehicles.scalars().all(),
        "status_filter": status,
        "vehicle_filter": vehicle_id,
        "statuses": [s.value for s in MaintenanceStatus],
        "user": current_user,
        "page": "maintenance",
        "can_write": has_permission(current_user, "maintenance", "write"),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_maintenance_form(
    request: Request,
    templates: TempDeps,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_permission("maintenance", "write")),
    db: AsyncSession = Depends(get_db),
):
    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    technicians = await db.execute(select(User).where(User.is_active == True))
    return templates.TemplateResponse("maintenance/maintenance_form.html", {
        "request": request,
        "user": current_user,
        "vehicles": vehicles.scalars().all(),
        "technicians": technicians.scalars().all(),
        "types": [t.value for t in MaintenanceType],
        "statuses": [s.value for s in MaintenanceStatus],
        "record": None,
        "selected_vehicle": vehicle_id,
        "today": date.today().isoformat(),
        "page": "maintenance",
    })


@router.post("/new")
async def create_maintenance(
    request: Request,
    vehicle_id: str = Form(...),
    title: str = Form(...),
    maintenance_type: str = Form("preventive"),
    status: str = Form("scheduled"),
    scheduled_date: str = Form(...),
    description: str = Form(""),
    cost: float = Form(0),
    vendor: str = Form(""),
    technician_id: str = Form(""),
    next_service_date: str = Form(""),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("maintenance", "write")),
    db: AsyncSession = Depends(get_db),
):
    record = MaintenanceRecord(
        vehicle_id=vehicle_id,
        title=title,
        maintenance_type=maintenance_type,
        status=status,
        scheduled_date=date.fromisoformat(scheduled_date),
        description=description or None,
        cost=cost,
        vendor=vendor or None,
        technician_id=technician_id or None,
        next_service_date=date.fromisoformat(next_service_date) if next_service_date else None,
        notes=notes or None,
    )
    db.add(record)

    # If in_maintenance, update vehicle status
    if status == "in_progress":
        veh = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
        v = veh.scalar_one_or_none()
        if v:
            v.status = "in_maintenance"

    log = ActivityLog(user_id=current_user.id, action="create_maintenance",
                      entity_type="maintenance", entity_id=record.id)
    db.add(log)
    await db.commit()

    return RedirectResponse(url="/maintenance", status_code=302)


@router.get("/{record_id}/edit", response_class=HTMLResponse)
async def edit_maintenance_form(
    record_id: str,
    templates: TempDeps,
    request: Request,
    current_user: User = Depends(require_permission("maintenance", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MaintenanceRecord).where(MaintenanceRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404)

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    technicians = await db.execute(select(User).where(User.is_active == True))

    return templates.TemplateResponse("maintenance/maintenance_form.html", {
        "request": request,
        "user": current_user,
        "record": record,
        "vehicles": vehicles.scalars().all(),
        "technicians": technicians.scalars().all(),
        "types": [t.value for t in MaintenanceType],
        "statuses": [s.value for s in MaintenanceStatus],
        "today": date.today().isoformat(),
        "page": "maintenance",
    })


@router.post("/{record_id}/edit")
async def update_maintenance(
    record_id: str,
    title: str = Form(...),
    maintenance_type: str = Form("preventive"),
    status: str = Form("scheduled"),
    scheduled_date: str = Form(...),
    completed_date: str = Form(""),
    description: str = Form(""),
    cost: float = Form(0),
    vendor: str = Form(""),
    technician_id: str = Form(""),
    next_service_date: str = Form(""),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("maintenance", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MaintenanceRecord).where(MaintenanceRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404)

    record.title = title
    record.maintenance_type = maintenance_type
    record.status = status
    record.scheduled_date = date.fromisoformat(scheduled_date)
    record.completed_date = date.fromisoformat(completed_date) if completed_date else None
    record.description = description or None
    record.cost = cost
    record.vendor = vendor or None
    record.technician_id = technician_id or None
    record.next_service_date = date.fromisoformat(next_service_date) if next_service_date else None
    record.notes = notes or None

    # If completed, restore vehicle status
    if status == "completed":
        veh = await db.execute(select(Vehicle).where(Vehicle.id == record.vehicle_id))
        v = veh.scalar_one_or_none()
        if v and v.status == "in_maintenance":
            v.status = "active"

    await db.commit()
    return RedirectResponse(url="/maintenance", status_code=302)


@router.post("/{record_id}/complete")
async def complete_maintenance(
    record_id: str,
    current_user: User = Depends(require_permission("maintenance", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MaintenanceRecord).where(MaintenanceRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404)

    record.status = "completed"
    record.completed_date = date.today()

    veh = await db.execute(select(Vehicle).where(Vehicle.id == record.vehicle_id))
    v = veh.scalar_one_or_none()
    if v and v.status == "in_maintenance":
        v.status = "active"

    await db.commit()

    if request.headers.get("HX-Request"):
        return HTMLResponse('<span class="badge badge-success">Completed</span>')
    return RedirectResponse(url="/maintenance", status_code=302)
