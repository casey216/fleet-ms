from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import date

from app.database import get_db
from app.models import Contract, ContractType, Vehicle, User, ActivityLog
from app.auth import require_user, require_permission, has_permission

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def contracts_list(
    request: Request,
    vehicle_id: Optional[str] = None,
    contract_type: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Contract, Vehicle)
        .join(Vehicle, Contract.vehicle_id == Vehicle.id)
        .order_by(Contract.end_date.asc().nullslast(), Contract.start_date.desc())
    )
    if vehicle_id:
        query = query.where(Contract.vehicle_id == vehicle_id)
    if contract_type:
        query = query.where(Contract.contract_type == contract_type)

    result = await db.execute(query)
    contracts = result.all()

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))

    return request.app.state.templates.TemplateResponse("contracts/contracts.html", {
        "request": request,
        "contracts": contracts,
        "vehicles": vehicles.scalars().all(),
        "vehicle_filter": vehicle_id,
        "type_filter": contract_type,
        "contract_types": [t.value for t in ContractType],
        "user": current_user,
        "page": "contracts",
        "can_write": has_permission(current_user, "contracts", "write"),
        "can_delete": has_permission(current_user, "contracts", "delete"),
        "today": date.today(),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_contract_form(
    request: Request,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_permission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
):
    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    return request.app.state.templates.TemplateResponse("contracts/contract_form.html", {
        "request": request,
        "user": current_user,
        "vehicles": vehicles.scalars().all(),
        "contract_types": [t.value for t in ContractType],
        "contract": None,
        "selected_vehicle": vehicle_id,
        "today": date.today().isoformat(),
        "page": "contracts",
    })


@router.post("/new")
async def create_contract(
    request: Request,
    vehicle_id: str = Form(...),
    contract_type: str = Form("purchase"),
    reference: str = Form(""),
    company: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(""),
    cost: float = Form(0),
    monthly_cost: float = Form(0),
    max_km: str = Form(""),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
):
    contract = Contract(
        vehicle_id=vehicle_id,
        contract_type=contract_type,
        reference=reference or None,
        company=company or None,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date) if end_date else None,
        cost=cost,
        monthly_cost=monthly_cost,
        max_km=int(max_km) if max_km else None,
        notes=notes or None,
    )
    db.add(contract)
    log = ActivityLog(user_id=current_user.id, action="create_contract",
                      entity_type="contract", entity_id=contract.id,
                      details={"vehicle_id": vehicle_id, "type": contract_type})
    db.add(log)
    await db.commit()
    return RedirectResponse(url=f"/contracts/{contract.id}", status_code=302)


@router.get("/{contract_id}", response_class=HTMLResponse)
async def contract_detail(
    contract_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Contract, Vehicle)
        .join(Vehicle, Contract.vehicle_id == Vehicle.id)
        .where(Contract.id == contract_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404)
    contract, vehicle = row

    return request.app.state.templates.TemplateResponse("contracts/contract_detail.html", {
        "request": request,
        "contract": contract,
        "vehicle": vehicle,
        "user": current_user,
        "page": "contracts",
        "can_write": has_permission(current_user, "contracts", "write"),
        "can_delete": has_permission(current_user, "contracts", "delete"),
        "today": date.today(),
    })


@router.get("/{contract_id}/edit", response_class=HTMLResponse)
async def edit_contract_form(
    contract_id: str,
    request: Request,
    current_user: User = Depends(require_permission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404)

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    return request.app.state.templates.TemplateResponse("contracts/contract_form.html", {
        "request": request,
        "user": current_user,
        "contract": contract,
        "vehicles": vehicles.scalars().all(),
        "contract_types": [t.value for t in ContractType],
        "today": date.today().isoformat(),
        "page": "contracts",
    })


@router.post("/{contract_id}/edit")
async def update_contract(
    contract_id: str,
    vehicle_id: str = Form(...),
    contract_type: str = Form("purchase"),
    reference: str = Form(""),
    company: str = Form(""),
    start_date: str = Form(...),
    end_date: str = Form(""),
    cost: float = Form(0),
    monthly_cost: float = Form(0),
    max_km: str = Form(""),
    notes: str = Form(""),
    current_user: User = Depends(require_permission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404)

    contract.vehicle_id = vehicle_id
    contract.contract_type = contract_type
    contract.reference = reference or None
    contract.company = company or None
    contract.start_date = date.fromisoformat(start_date)
    contract.end_date = date.fromisoformat(end_date) if end_date else None
    contract.cost = cost
    contract.monthly_cost = monthly_cost
    contract.max_km = int(max_km) if max_km else None
    contract.notes = notes or None

    log = ActivityLog(user_id=current_user.id, action="update_contract",
                      entity_type="contract", entity_id=contract_id)
    db.add(log)
    await db.commit()
    return RedirectResponse(url=f"/contracts/{contract_id}", status_code=302)


@router.post("/{contract_id}/delete")
async def delete_contract(
    contract_id: str,
    current_user: User = Depends(require_permission("contracts", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404)
    await db.delete(contract)
    log = ActivityLog(user_id=current_user.id, action="delete_contract",
                      entity_type="contract", entity_id=contract_id)
    db.add(log)
    await db.commit()
    return RedirectResponse(url="/contracts", status_code=302)