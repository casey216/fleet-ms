from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Vehicle, FuelLog, MaintenanceRecord, Alert, User
from app.auth import require_user

router = APIRouter()


@router.get("/alerts/count", response_class=HTMLResponse)
async def alerts_count(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    count = await db.scalar(
        select(func.count(Alert.id)).where(Alert.is_dismissed == False)
    ) or 0

    if count == 0:
        return HTMLResponse(
            '<a href="/alerts" class="topbar-bell" style="position:relative;color:var(--text-secondary);'
            'text-decoration:none;font-size:16px;padding:6px;" data-tooltip="No active alerts">'
            '<i class="fa-regular fa-bell"></i></a>'
        )

    return HTMLResponse(
        f'<a href="/alerts" class="topbar-bell" style="position:relative;color:var(--text-secondary);'
        f'text-decoration:none;font-size:16px;padding:6px;display:inline-block;" data-tooltip="{count} active alert{"s" if count != 1 else ""}">'
        f'<i class="fa-solid fa-bell" style="color:var(--warning);"></i>'
        f'<span style="position:absolute;top:0;right:0;background:var(--danger);color:#fff;'
        f'font-size:9px;font-weight:700;min-width:14px;height:14px;border-radius:7px;'
        f'display:flex;align-items:center;justify-content:center;padding:0 3px;line-height:1;">'
        f'{count if count < 10 else "9+"}</span></a>'
    )


@router.get("/vehicles/search")
async def search_vehicles(
    q: str = "",
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Vehicle).where(
            Vehicle.license_plate.ilike(f"%{q}%") |
            Vehicle.make.ilike(f"%{q}%") |
            Vehicle.model.ilike(f"%{q}%")
        ).limit(10)
    )
    vehicles = result.scalars().all()
    return JSONResponse([
        {"id": v.id, "label": f"{v.license_plate} — {v.make} {v.model} ({v.year})"}
        for v in vehicles
    ])


@router.get("/stats/summary")
async def stats_summary(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count(Vehicle.id))) or 0
    fuel_total = await db.scalar(select(func.sum(FuelLog.total_cost))) or 0
    maint_total = await db.scalar(select(func.sum(MaintenanceRecord.cost))) or 0
    return JSONResponse({
        "total_vehicles": total,
        "total_fuel_cost": float(fuel_total),
        "total_maintenance_cost": float(maint_total),
    })