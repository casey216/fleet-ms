from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import date, timedelta

from app.database import get_db
from app.models import (
    Vehicle, VehicleStatus, FuelLog, MaintenanceRecord,
    MaintenanceStatus, Alert, User, ActivityLog
)
from app.auth import require_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):

    # Stats
    total_vehicles = await db.scalar(select(func.count(Vehicle.id)))
    active_vehicles = await db.scalar(
        select(func.count(Vehicle.id)).where(Vehicle.status == VehicleStatus.active)
    )
    in_maintenance = await db.scalar(
        select(func.count(Vehicle.id)).where(Vehicle.status == VehicleStatus.in_maintenance)
    )

    # Fuel cost this month
    first_of_month = date.today().replace(day=1)
    monthly_fuel_cost = await db.scalar(
        select(func.sum(FuelLog.total_cost)).where(FuelLog.date >= first_of_month)
    ) or 0

    # Pending maintenance
    pending_maintenance = await db.scalar(
        select(func.count(MaintenanceRecord.id)).where(
            MaintenanceRecord.status.in_([MaintenanceStatus.scheduled, MaintenanceStatus.in_progress])
        )
    )

    # Upcoming maintenance (next 7 days)
    upcoming = await db.execute(
        select(MaintenanceRecord, Vehicle)
        .join(Vehicle, MaintenanceRecord.vehicle_id == Vehicle.id)
        .where(
            MaintenanceRecord.status == MaintenanceStatus.scheduled,
            MaintenanceRecord.scheduled_date <= date.today() + timedelta(days=7),
        )
        .order_by(MaintenanceRecord.scheduled_date)
        .limit(5)
    )
    upcoming_maintenance = upcoming.all()

    # Recent fuel logs
    recent_fuel = await db.execute(
        select(FuelLog, Vehicle)
        .join(Vehicle, FuelLog.vehicle_id == Vehicle.id)
        .order_by(FuelLog.date.desc())
        .limit(5)
    )
    recent_fuel_logs = recent_fuel.all()

    # Recent activity
    recent_activity = await db.execute(
        select(ActivityLog, User)
        .join(User, ActivityLog.user_id == User.id, isouter=True)
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
    )
    activity = recent_activity.all()

    # Monthly fuel chart data (last 6 months)
    fuel_chart = []
    for i in range(5, -1, -1):
        month_start = (date.today().replace(day=1) - timedelta(days=30 * i))
        month_start = month_start.replace(day=1)
        if i == 0:
            month_end = date.today()
        else:
            next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = next_month - timedelta(days=1)

        cost = await db.scalar(
            select(func.sum(FuelLog.total_cost)).where(
                and_(FuelLog.date >= month_start, FuelLog.date <= month_end)
            )
        ) or 0
        fuel_chart.append({
            "month": month_start.strftime("%b %Y"),
            "cost": float(cost),
        })

    # Vehicle status breakdown
    status_counts = {
        "active": active_vehicles or 0,
        "in_maintenance": in_maintenance or 0,
        "out_of_service": await db.scalar(
            select(func.count(Vehicle.id)).where(Vehicle.status == VehicleStatus.out_of_service)
        ) or 0,
        "reserved": await db.scalar(
            select(func.count(Vehicle.id)).where(Vehicle.status == VehicleStatus.reserved)
        ) or 0,
    }

    # Unread alerts
    alerts = await db.execute(
        select(Alert).where(Alert.is_dismissed == False).order_by(Alert.created_at.desc()).limit(5)
    )
    recent_alerts = alerts.scalars().all()

    return request.app.state.templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "total_vehicles": total_vehicles or 0,
        "active_vehicles": active_vehicles or 0,
        "in_maintenance": in_maintenance or 0,
        "monthly_fuel_cost": float(monthly_fuel_cost),
        "pending_maintenance": pending_maintenance or 0,
        "upcoming_maintenance": upcoming_maintenance,
        "recent_fuel_logs": recent_fuel_logs,
        "activity": activity,
        "fuel_chart": fuel_chart,
        "status_counts": status_counts,
        "recent_alerts": recent_alerts,
        "page": "dashboard",
    })