from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import date, timedelta

from app.database import get_db
from app.models import InsurancePolicy, Vehicle, User, ActivityLog, Alert, AlertType
from app.auth import require_user, require_permission, has_permission

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def insurance_list(
    request: Request,
    vehicle_id: Optional[str] = None,
    expiring: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(InsurancePolicy, Vehicle)
        .join(Vehicle, InsurancePolicy.vehicle_id == Vehicle.id)
        .order_by(InsurancePolicy.end_date.asc())
    )
    if vehicle_id:
        query = query.where(InsurancePolicy.vehicle_id == vehicle_id)
    if expiring == "30":
        cutoff = date.today() + timedelta(days=30)
        query = query.where(InsurancePolicy.end_date <= cutoff)

    result = await db.execute(query)
    policies = result.all()

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))

    # Count expiring soon (≤30 days)
    expiring_count = sum(
        1 for p, v in policies
        if p.end_date and (p.end_date - date.today()).days <= 30
    )

    return request.app.state.templates.TemplateResponse("insurance/insurance.html", {
        "request": request,
        "policies": policies,
        "vehicles": vehicles.scalars().all(),
        "vehicle_filter": vehicle_id,
        "expiring_filter": expiring,
        "expiring_count": expiring_count,
        "user": current_user,
        "page": "insurance",
        "can_write": has_permission(current_user, "insurance", "write"),
        "can_delete": has_permission(current_user, "insurance", "delete"),
        "today": date.today(),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_insurance_form(
    request: Request,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_permission("insurance", "write")),
    db: AsyncSession = Depends(get_db),
):
    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    return request.app.state.templates.TemplateResponse("insurance/insurance_form.html", {
        "request": request,
        "user": current_user,
        "vehicles": vehicles.scalars().all(),
        "policy": None,
        "selected_vehicle": vehicle_id,
        "today": date.today().isoformat(),
        "page": "insurance",
    })


@router.post("/new")
async def create_insurance(
    request: Request,
    vehicle_id: str = Form(...),
    policy_number: str = Form(...),
    insurer: str = Form(...),
    coverage_type: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(...),
    premium: float = Form(0),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("insurance", "write")),
    db: AsyncSession = Depends(get_db),
):
    policy = InsurancePolicy(
        vehicle_id=vehicle_id,
        policy_number=policy_number,
        insurer=insurer,
        coverage_type=coverage_type or None,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date),
        premium=premium,
        notes=notes or None,
    )
    db.add(policy)
    await db.flush()

    # Auto-create alert if expiring within 60 days
    exp = date.fromisoformat(end_date)
    days_left = (exp - date.today()).days
    if days_left <= 60:
        veh = await db.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
        v = veh.scalar_one_or_none()
        plate = v.license_plate if v else vehicle_id
        db.add(Alert(
            vehicle_id=vehicle_id,
            alert_type=AlertType.insurance_expiry,
            title=f"Insurance Expiring — {plate}",
            message=f"Policy {policy_number} with {insurer} expires in {days_left} days.",
            due_date=exp,
        ))

    log = ActivityLog(user_id=current_user.id, action="create_insurance",
                      entity_type="insurance", entity_id=policy.id)
    db.add(log)
    await db.commit()
    return RedirectResponse(url=f"/insurance/{policy.id}", status_code=302)


@router.get("/{policy_id}", response_class=HTMLResponse)
async def insurance_detail(
    policy_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InsurancePolicy, Vehicle)
        .join(Vehicle, InsurancePolicy.vehicle_id == Vehicle.id)
        .where(InsurancePolicy.id == policy_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404)
    policy, vehicle = row

    return request.app.state.templates.TemplateResponse("insurance/insurance_detail.html", {
        "request": request,
        "policy": policy,
        "vehicle": vehicle,
        "user": current_user,
        "page": "insurance",
        "can_write": has_permission(current_user, "insurance", "write"),
        "can_delete": has_permission(current_user, "insurance", "delete"),
        "today": date.today(),
    })


@router.get("/{policy_id}/edit", response_class=HTMLResponse)
async def edit_insurance_form(
    policy_id: str,
    request: Request,
    current_user: User = Depends(require_permission("insurance", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404)

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    return request.app.state.templates.TemplateResponse("insurance/insurance_form.html", {
        "request": request,
        "user": current_user,
        "policy": policy,
        "vehicles": vehicles.scalars().all(),
        "today": date.today().isoformat(),
        "page": "insurance",
    })


@router.post("/{policy_id}/edit")
async def update_insurance(
    policy_id: str,
    vehicle_id: str = Form(...),
    policy_number: str = Form(...),
    insurer: str = Form(...),
    coverage_type: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(...),
    premium: float = Form(0),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("insurance", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404)

    policy.vehicle_id = vehicle_id
    policy.policy_number = policy_number
    policy.insurer = insurer
    policy.coverage_type = coverage_type or None
    policy.start_date = date.fromisoformat(start_date)
    policy.end_date = date.fromisoformat(end_date)
    policy.premium = premium
    policy.notes = notes or None

    log = ActivityLog(user_id=current_user.id, action="update_insurance",
                      entity_type="insurance", entity_id=policy_id)
    db.add(log)
    await db.commit()
    return RedirectResponse(url=f"/insurance/{policy_id}", status_code=302)


@router.post("/{policy_id}/delete")
async def delete_insurance(
    policy_id: str,
    current_user: User = Depends(require_permission("insurance", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InsurancePolicy).where(InsurancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404)
    await db.delete(policy)
    log = ActivityLog(user_id=current_user.id, action="delete_insurance",
                      entity_type="insurance", entity_id=policy_id)
    db.add(log)
    await db.commit()
    return RedirectResponse(url="/insurance", status_code=302)