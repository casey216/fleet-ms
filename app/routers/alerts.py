from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, Annotated
from datetime import date

from app.database import get_db
from app.models import Alert, AlertType, Vehicle, User, ActivityLog
from app.auth import require_user, require_permission, has_permission
from app.dependencies import get_template


TempDeps = Annotated[Jinja2Templates, Depends(get_template)]

router = APIRouter()



@router.get("", response_class=HTMLResponse)
async def alerts_list(
    request: Request,
    templates: TempDeps,
    show_dismissed: Optional[str] = None,
    alert_type: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Alert, Vehicle)
        .join(Vehicle, Alert.vehicle_id == Vehicle.id, isouter=True)
        .order_by(Alert.is_dismissed.asc(), Alert.due_date.asc().nullslast(), Alert.created_at.desc())
    )
    if not show_dismissed:
        query = query.where(Alert.is_dismissed == False)
    if alert_type:
        query = query.where(Alert.alert_type == alert_type)

    result = await db.execute(query)
    alerts = result.all()

    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))

    # Badge counts
    active_count = await db.scalar(
        select(func.count(Alert.id))
        .where(Alert.is_dismissed == False)
    ) or 0

    return templates.TemplateResponse("alerts/alerts.html", {
        "request": request,
        "alerts": alerts,
        "vehicles": vehicles.scalars().all(),
        "alert_types": [t.value for t in AlertType],
        "type_filter": alert_type,
        "show_dismissed": show_dismissed,
        "active_count": active_count,
        "user": current_user,
        "page": "alerts",
        "can_write": has_permission(current_user, "contracts", "write"),
        "today": date.today(),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_alert_form(
    request: Request,
    templates: TempDeps,
    vehicle_id: Optional[str] = None,
    current_user: User = Depends(require_permission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
):
    vehicles = await db.execute(select(Vehicle).order_by(Vehicle.make))
    return templates.TemplateResponse("alerts/alert_form.html", {
        "request": request,
        "user": current_user,
        "vehicles": vehicles.scalars().all(),
        "alert_types": [t.value for t in AlertType],
        "alert": None,
        "selected_vehicle": vehicle_id,
        "today": date.today().isoformat(),
        "page": "alerts",
    })


@router.post("/new")
async def create_alert(
    request: Request,
    vehicle_id: str = Form(""),
    alert_type: str = Form(...),
    title: str = Form(...),
    message: str = Form(""),
    due_date: str = Form(""),
    current_user: User = Depends(require_permission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
):
    alert = Alert(
        vehicle_id=vehicle_id or None,
        alert_type=alert_type,
        title=title,
        message=message or None,
        due_date=date.fromisoformat(due_date) if due_date else None,
    )
    db.add(alert)
    log = ActivityLog(user_id=current_user.id, action="create_alert",
                      entity_type="alert", entity_id=alert.id)
    db.add(log)
    await db.commit()
    return RedirectResponse(url="/alerts", status_code=302)


@router.post("/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404)
    alert.is_dismissed = True
    alert.is_read = True
    await db.commit()

    if request.headers.get("HX-Request"):
        return HTMLResponse(
            '<span class="badge badge-ghost">Dismissed</span>'
        )
    return RedirectResponse(url="/alerts", status_code=302)


@router.post("/{alert_id}/undismiss")
async def undismiss_alert(
    alert_id: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404)
    alert.is_dismissed = False
    await db.commit()
    return RedirectResponse(url="/alerts?show_dismissed=1", status_code=302)


@router.post("/{alert_id}/delete")
async def delete_alert(
    alert_id: str,
    current_user: User = Depends(require_permission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404)
    await db.delete(alert)
    await db.commit()
    return RedirectResponse(url="/alerts", status_code=302)


@router.post("/dismiss-all")
async def dismiss_all(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Alert).where(Alert.is_dismissed == False))
    for alert in result.scalars().all():
        alert.is_dismissed = True
        alert.is_read = True
    await db.commit()
    return RedirectResponse(url="/alerts", status_code=302)