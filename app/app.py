from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base
from app.routers import (
    auth, vehicles, drivers, fuel, maintenance, reports,
    settings as settings_router, dashboard, api,
    contracts, insurance, alerts, odometer,
)

import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Custom template filters
def format_currency(value):
    if value is None:
        return "—"
    return f"${float(value):,.2f}"

def format_km(value):
    if value is None:
        return "—"
    return f"{int(value):,} km"

def format_date(value):
    if value is None:
        return "—"
    if hasattr(value, 'strftime'):
        return value.strftime("%b %d, %Y")
    return str(value)

def days_until(value):
    if value is None:
        return None
    from datetime import date
    if hasattr(value, 'date'):
        d = value.date()
    else:
        d = value
    delta = (d - date.today()).days
    return delta

templates.env.filters["currency"] = format_currency
templates.env.filters["km"] = format_km
templates.env.filters["fmt_date"] = format_date
templates.env.filters["days_until"] = days_until

# Inject templates into routers that need it
app.state.templates = templates

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(vehicles.router, prefix="/vehicles", tags=["vehicles"])
app.include_router(drivers.router, prefix="/drivers", tags=["drivers"])
app.include_router(fuel.router, prefix="/fuel", tags=["fuel"])
app.include_router(maintenance.router, prefix="/maintenance", tags=["maintenance"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(settings_router.router, prefix="/settings", tags=["settings"])
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
app.include_router(insurance.router, prefix="/insurance", tags=["insurance"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
app.include_router(odometer.router, prefix="/odometer", tags=["odometer"])


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    return templates.TemplateResponse("403.html", {"request": request}, status_code=403)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app="app.app:app")