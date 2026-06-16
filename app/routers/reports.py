from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import date, timedelta

from app.database import get_db
from app.models import Vehicle, FuelLog, MaintenanceRecord, User
from app.auth import require_user, has_permission

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def reports(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if not has_permission(current_user, "reports", "read"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403)

    # Fleet cost summary (last 12 months)
    monthly_data = []
    for i in range(11, -1, -1):
        month_start = (date.today().replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        if i == 0:
            month_end = date.today()
        else:
            next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = next_month - timedelta(days=1)

        fuel = await db.scalar(
            select(func.sum(FuelLog.total_cost)).where(
                and_(FuelLog.date >= month_start, FuelLog.date <= month_end)
            )
        ) or 0
        maint = await db.scalar(
            select(func.sum(MaintenanceRecord.cost)).where(
                and_(
                    MaintenanceRecord.scheduled_date >= month_start,
                    MaintenanceRecord.scheduled_date <= month_end,
                )
            )
        ) or 0
        monthly_data.append({
            "month": month_start.strftime("%b %Y"),
            "fuel": float(fuel),
            "maintenance": float(maint),
            "total": float(fuel) + float(maint),
        })

    # Top 5 vehicles by fuel cost
    top_fuel = await db.execute(
        select(Vehicle, func.sum(FuelLog.total_cost).label("total"))
        .join(FuelLog, Vehicle.id == FuelLog.vehicle_id)
        .group_by(Vehicle.id)
        .order_by(func.sum(FuelLog.total_cost).desc())
        .limit(5)
    )
    top_fuel_vehicles = top_fuel.all()

    # Top 5 vehicles by maintenance cost
    top_maint = await db.execute(
        select(Vehicle, func.sum(MaintenanceRecord.cost).label("total"))
        .join(MaintenanceRecord, Vehicle.id == MaintenanceRecord.vehicle_id)
        .group_by(Vehicle.id)
        .order_by(func.sum(MaintenanceRecord.cost).desc())
        .limit(5)
    )
    top_maint_vehicles = top_maint.all()

    # Avg fuel consumption (liters per 100km) per vehicle
    # Total fuel cost this year
    year_start = date.today().replace(month=1, day=1)
    ytd_fuel = await db.scalar(
        select(func.sum(FuelLog.total_cost)).where(FuelLog.date >= year_start)
    ) or 0
    ytd_maintenance = await db.scalar(
        select(func.sum(MaintenanceRecord.cost)).where(MaintenanceRecord.scheduled_date >= year_start)
    ) or 0

    total_vehicles = await db.scalar(select(func.count(Vehicle.id))) or 0
    total_fuel_liters = await db.scalar(select(func.sum(FuelLog.liters))) or 0

    return request.app.state.templates.TemplateResponse("reports/reports.html", {
        "request": request,
        "user": current_user,
        "monthly_data": monthly_data,
        "top_fuel_vehicles": top_fuel_vehicles,
        "top_maint_vehicles": top_maint_vehicles,
        "ytd_fuel": float(ytd_fuel),
        "ytd_maintenance": float(ytd_maintenance),
        "total_vehicles": total_vehicles,
        "total_fuel_liters": float(total_fuel_liters),
        "page": "reports",
    })