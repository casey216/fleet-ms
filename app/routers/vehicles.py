from fastapi import APIRouter, Depends, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func
from typing import Optional, Annotated
from datetime import date
import re

from app.database import get_db
from app.models import (
    Vehicle, VehicleStatus, FuelType, User, ActivityLog, FuelLog,
    MaintenanceRecord, Contract, InsurancePolicy, OdometerLog
)
from app.auth import require_user, require_permission, has_permission
from app.dependencies import get_template


TempDeps = Annotated[Jinja2Templates, Depends(get_template)]

router = APIRouter()


def parse_unique_violation(detail: str):
    match = re.search(r"\((.*?)\)=\((.*?)\)", detail)
    if match:
        field, value = match.group(1), match.group(2)
        return f"{field.replace('_', ' ').title()} '{value}' already exists!"
    return None


@router.get("", response_class=HTMLResponse)
async def vehicles_list(
    request: Request,
    templates: TempDeps,
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Vehicle)
    if status:
        query = query.where(Vehicle.status == status)
    if search:
        query = query.where(
            Vehicle.license_plate.ilike(f"%{search}%") |
            Vehicle.make.ilike(f"%{search}%") |
            Vehicle.model.ilike(f"%{search}%")
        )
    query = query.order_by(Vehicle.make, Vehicle.model)

    result = await db.execute(query)
    vehicles = result.scalars().all()

    # Get driver names
    driver_ids = [v.driver_id for v in vehicles if v.driver_id]
    drivers = {}
    if driver_ids:
        driver_result = await db.execute(select(User).where(User.id.in_(driver_ids)))
        for d in driver_result.scalars().all():
            drivers[d.id] = d

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("fleet/vehicle_rows.html", {
            "request": request,
            "vehicles": vehicles,
            "drivers": drivers,
            "user": current_user,
        })

    return templates.TemplateResponse("fleet/vehicles.html", {
        "request": request,
        "vehicles": vehicles,
        "drivers": drivers,
        "user": current_user,
        "status_filter": status,
        "search": search,
        "page": "vehicles",
        "can_write": has_permission(current_user, "vehicles", "write"),
        "can_delete": has_permission(current_user, "vehicles", "delete"),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_vehicle_form(
    request: Request,
    templates: TempDeps,
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    drivers = await db.execute(select(User).where(User.is_active == True))
    return templates.TemplateResponse("fleet/vehicle_form.html", {
        "request": request,
        "user": current_user,
        "drivers": drivers.scalars().all(),
        "fuel_types": [f.value for f in FuelType],
        "statuses": [s.value for s in VehicleStatus],
        "vehicle": None,
        "page": "vehicles",
    })


@router.post("/new")
async def create_vehicle(
    request: Request,
    templates: TempDeps,
    license_plate: str = Form(...),
    make: str = Form(...),
    model: str = Form(...),
    year: int = Form(...),
    color: str = Form(""),
    vin: str = Form(""),
    fuel_type: str = Form("petrol"),
    status: str = Form("active"),
    odometer: int = Form(0),
    seats: int = Form(5),
    driver_id: str = Form(""),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    vehicle = Vehicle(
        license_plate=license_plate.upper(),
        make=make,
        model=model,
        year=year,
        color=color or None,
        vin=vin or None,
        fuel_type=fuel_type,
        status=status,
        odometer=odometer,
        seats=seats,
        driver_id=driver_id or None,
        notes=notes or None,
    )
    try:
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)

        log = ActivityLog(user_id=current_user.id, action="create_vehicle",
                        entity_type="vehicle", entity_id=vehicle.id,
                        details={"plate": license_plate})
        db.add(log)
        await db.commit()
    except IntegrityError as e:
        detail: str = e.orig.args[0]
        errors = [parse_unique_violation(detail)]
        return templates.TemplateResponse("errors.html", {
            "request": request,
            "errors": errors
        })
    
    resp = Response(status_code=204)
    resp.headers["HX-Redirect"] = f"/vehicles/{vehicle.id}"
    return resp



@router.get("/{vehicle_id}", response_class=HTMLResponse)
async def vehicle_detail(
    vehicle_id: str,
    request: Request,
    templates: TempDeps,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404)

    driver = None
    if vehicle.driver_id:
        dr = await db.execute(select(User).where(User.id == vehicle.driver_id))
        driver = dr.scalar_one_or_none()

    # Recent fuel logs
    fuel_result = await db.execute(
        select(FuelLog).where(FuelLog.vehicle_id == vehicle_id)
        .order_by(FuelLog.date.desc()).limit(10)
    )
    fuel_logs = fuel_result.scalars().all()

    # Maintenance records
    maint_result = await db.execute(
        select(MaintenanceRecord).where(MaintenanceRecord.vehicle_id == vehicle_id)
        .order_by(MaintenanceRecord.scheduled_date.desc()).limit(10)
    )
    maintenance = maint_result.scalars().all()

    # Total costs
    total_fuel = await db.scalar(
        select(func.sum(FuelLog.total_cost)).where(FuelLog.vehicle_id == vehicle_id)
    ) or 0
    total_maintenance = await db.scalar(
        select(func.sum(MaintenanceRecord.cost)).where(MaintenanceRecord.vehicle_id == vehicle_id)
    ) or 0

    # Contracts
    contracts_result = await db.execute(
        select(Contract).where(Contract.vehicle_id == vehicle_id)
        .order_by(Contract.start_date.desc())
    )
    contracts = contracts_result.scalars().all()

    # Insurance policies
    insurance_result = await db.execute(
        select(InsurancePolicy).where(InsurancePolicy.vehicle_id == vehicle_id)
        .order_by(InsurancePolicy.end_date.desc())
    )
    insurance_policies = insurance_result.scalars().all()

    # Odometer logs
    odo_result = await db.execute(
        select(OdometerLog).where(OdometerLog.vehicle_id == vehicle_id)
        .order_by(OdometerLog.date.desc()).limit(10)
    )
    odometer_logs = odo_result.scalars().all()

    return templates.TemplateResponse("fleet/vehicle_detail.html", {
        "request": request,
        "vehicle": vehicle,
        "driver": driver,
        "fuel_logs": fuel_logs,
        "maintenance": maintenance,
        "contracts": contracts,
        "insurance_policies": insurance_policies,
        "odometer_logs": odometer_logs,
        "total_fuel_cost": float(total_fuel),
        "total_maintenance_cost": float(total_maintenance),
        "user": current_user,
        "page": "vehicles",
        "can_write": has_permission(current_user, "vehicles", "write"),
        "can_delete": has_permission(current_user, "vehicles", "delete"),
        "today": date.today(),
    })


@router.get("/{vehicle_id}/edit", response_class=HTMLResponse)
async def edit_vehicle_form(
    vehicle_id: str,
    request: Request,
    templates: TempDeps,
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404)

    drivers = await db.execute(select(User).where(User.is_active == True))
    return templates.TemplateResponse("fleet/vehicle_form.html", {
        "request": request,
        "vehicle": vehicle,
        "user": current_user,
        "drivers": drivers.scalars().all(),
        "fuel_types": [f.value for f in FuelType],
        "statuses": [s.value for s in VehicleStatus],
        "page": "vehicles",
    })


@router.post("/{vehicle_id}/edit")
async def update_vehicle(
    vehicle_id: str,
    request: Request,
    license_plate: str = Form(...),
    make: str = Form(...),
    model: str = Form(...),
    year: int = Form(...),
    color: str = Form(""),
    vin: str = Form(""),
    fuel_type: str = Form("petrol"),
    status: str = Form("active"),
    odometer: int = Form(0),
    seats: int = Form(5),
    driver_id: str = Form(""),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("vehicles", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404)

    vehicle.license_plate = license_plate.upper()
    vehicle.make = make
    vehicle.model = model
    vehicle.year = year
    vehicle.color = color or None
    vehicle.vin = vin or None
    vehicle.fuel_type = fuel_type
    vehicle.status = status
    vehicle.odometer = odometer
    vehicle.seats = seats
    vehicle.driver_id = driver_id or None
    vehicle.notes = notes or None

    await db.commit()

    log = ActivityLog(user_id=current_user.id, action="update_vehicle",
                      entity_type="vehicle", entity_id=vehicle_id)
    db.add(log)
    await db.commit()

    return RedirectResponse(url=f"/vehicles/{vehicle_id}", status_code=302)


@router.post("/{vehicle_id}/delete")
async def delete_vehicle(
    vehicle_id: str,
    current_user: User = Depends(require_permission("vehicles", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    vehicle = result.scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404)

    await db.delete(vehicle)
    log = ActivityLog(user_id=current_user.id, action="delete_vehicle",
                      entity_type="vehicle", entity_id=vehicle_id)
    db.add(log)
    await db.commit()

    return RedirectResponse(url="/vehicles", status_code=302)