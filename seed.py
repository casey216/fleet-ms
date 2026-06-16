#!/usr/bin/env python3
"""
Seed script — populates the DB with demo data.
Run: python seed.py
"""
import asyncio
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.config import settings
from app.database import Base
from app.models import (
    User, Vehicle, FuelLog, MaintenanceRecord, Contract, InsurancePolicy,
    Alert, ActivityLog, OdometerLog, UserRole, VehicleStatus, FuelType,
    MaintenanceStatus, MaintenanceType, ContractType, AlertType
)
from app.auth import get_password_hash

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession() as db:
        # Check if already seeded
        existing = await db.execute(select(User))
        if existing.first():
            print("⚠️  Database already has data. Skipping seed.")
            return

        print("🌱 Seeding database…")

        # ── Users ────────────────────────────────────────────────────────────
        admin = User(
            full_name="Alex Administrator",
            email="admin@fleethq.com",
            username="admin",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.admin,
            phone="+1 555 100 0001",
            department="Management",
        )
        manager = User(
            full_name="Morgan Fleet",
            email="manager@fleethq.com",
            username="morgan",
            hashed_password=get_password_hash("manager123"),
            role=UserRole.fleet_manager,
            phone="+1 555 100 0002",
            department="Operations",
        )
        driver1 = User(
            full_name="Jordan Driver",
            email="jordan@fleethq.com",
            username="jordan",
            hashed_password=get_password_hash("driver123"),
            role=UserRole.driver,
            phone="+1 555 100 0003",
            department="Delivery",
        )
        driver2 = User(
            full_name="Casey Roads",
            email="casey@fleethq.com",
            username="casey",
            hashed_password=get_password_hash("driver123"),
            role=UserRole.driver,
            phone="+1 555 100 0004",
            department="Delivery",
        )
        viewer = User(
            full_name="Sam Viewer",
            email="viewer@fleethq.com",
            username="samviewer",
            hashed_password=get_password_hash("viewer123"),
            role=UserRole.viewer,
            department="Finance",
        )

        for u in [admin, manager, driver1, driver2, viewer]:
            db.add(u)
        await db.flush()

        # ── Vehicles ─────────────────────────────────────────────────────────
        vehicles_data = [
            dict(license_plate="TRK-001", make="Toyota", model="HiLux", year=2022,
                 color="White", fuel_type=FuelType.diesel, odometer=34500, seats=5,
                 driver_id=driver1.id),
            dict(license_plate="TRK-002", make="Ford", model="Transit", year=2021,
                 color="Silver", fuel_type=FuelType.diesel, odometer=61200, seats=3,
                 driver_id=driver2.id),
            dict(license_plate="CAR-001", make="Honda", model="CR-V", year=2023,
                 color="Pearl White", fuel_type=FuelType.petrol, odometer=12800, seats=5,
                 driver_id=manager.id),
            dict(license_plate="VAN-001", make="Mercedes", model="Sprinter", year=2020,
                 color="Graphite", fuel_type=FuelType.diesel, odometer=89300, seats=2,
                 status=VehicleStatus.in_maintenance),
            dict(license_plate="EV-001", make="Tesla", model="Model 3", year=2023,
                 color="Midnight Black", fuel_type=FuelType.electric, odometer=8500, seats=5),
            dict(license_plate="TRK-003", make="Isuzu", model="D-Max", year=2019,
                 color="Red", fuel_type=FuelType.diesel, odometer=112000, seats=5,
                 status=VehicleStatus.out_of_service),
        ]

        vehicles = []
        for vd in vehicles_data:
            v = Vehicle(**vd)
            db.add(v)
            vehicles.append(v)
        await db.flush()

        today = date.today()

        # ── Fuel logs ─────────────────────────────────────────────────────────
        fuel_entries = [
            (vehicles[0], today - timedelta(days=2),  55.0, 1.820, 34500),
            (vehicles[0], today - timedelta(days=18), 52.3, 1.795, 33800),
            (vehicles[0], today - timedelta(days=35), 48.7, 1.810, 33100),
            (vehicles[1], today - timedelta(days=5),  70.2, 1.830, 61200),
            (vehicles[1], today - timedelta(days=22), 68.5, 1.815, 60400),
            (vehicles[1], today - timedelta(days=40), 65.0, 1.800, 59600),
            (vehicles[2], today - timedelta(days=8),  45.0, 1.750, 12800),
            (vehicles[2], today - timedelta(days=30), 42.1, 1.720, 12200),
            (vehicles[4], today - timedelta(days=10), 0,    0,     8500),
        ]

        for v, d, liters, cpl, odo in fuel_entries:
            if liters > 0:
                db.add(FuelLog(
                    vehicle_id=v.id,
                    logged_by=driver1.id,
                    date=d,
                    liters=liters,
                    cost_per_liter=cpl,
                    total_cost=round(liters * cpl, 2),
                    odometer=odo,
                    station="Shell Service Station",
                    full_tank=True,
                ))

        # ── Maintenance records ───────────────────────────────────────────────
        maintenance_data = [
            dict(vehicle_id=vehicles[0].id, title="Oil Change & Filter", maintenance_type=MaintenanceType.oil_change,
                 status=MaintenanceStatus.completed, scheduled_date=today - timedelta(days=30),
                 completed_date=today - timedelta(days=29), cost=180, vendor="QuickLube Auto"),
            dict(vehicle_id=vehicles[1].id, title="Brake Inspection", maintenance_type=MaintenanceType.inspection,
                 status=MaintenanceStatus.completed, scheduled_date=today - timedelta(days=45),
                 completed_date=today - timedelta(days=44), cost=250, vendor="BrakeMaster"),
            dict(vehicle_id=vehicles[3].id, title="Transmission Repair", maintenance_type=MaintenanceType.corrective,
                 status=MaintenanceStatus.in_progress, scheduled_date=today - timedelta(days=3),
                 cost=1200, vendor="AutoFix Workshop"),
            dict(vehicle_id=vehicles[0].id, title="Tyre Rotation", maintenance_type=MaintenanceType.tire,
                 status=MaintenanceStatus.scheduled, scheduled_date=today + timedelta(days=5),
                 cost=120, vendor="TyrePlus"),
            dict(vehicle_id=vehicles[1].id, title="Annual Inspection", maintenance_type=MaintenanceType.inspection,
                 status=MaintenanceStatus.scheduled, scheduled_date=today + timedelta(days=12),
                 cost=300, vendor="AutoCheck"),
            dict(vehicle_id=vehicles[2].id, title="Oil Change", maintenance_type=MaintenanceType.oil_change,
                 status=MaintenanceStatus.scheduled, scheduled_date=today + timedelta(days=20),
                 cost=160, vendor="QuickLube Auto"),
            dict(vehicle_id=vehicles[5].id, title="Engine Overhaul", maintenance_type=MaintenanceType.corrective,
                 status=MaintenanceStatus.scheduled, scheduled_date=today + timedelta(days=2),
                 cost=3500, vendor="Heavy Duty Workshop"),
        ]

        for md in maintenance_data:
            db.add(MaintenanceRecord(**md))

        # ── Odometer logs ────────────────────────────────────────────────────
        odo_entries = [
            (vehicles[0], today - timedelta(days=60), 32000),
            (vehicles[0], today - timedelta(days=30), 33100),
            (vehicles[0], today - timedelta(days=2),  34500),
            (vehicles[1], today - timedelta(days=40), 59600),
            (vehicles[1], today - timedelta(days=5),  61200),
        ]
        for v, d, val in odo_entries:
            db.add(OdometerLog(vehicle_id=v.id, date=d, value=val))

        # ── Contracts ────────────────────────────────────────────────────────
        db.add(Contract(
            vehicle_id=vehicles[0].id, contract_type=ContractType.lease,
            reference="LEASE-2022-001", company="AutoLease Corp",
            start_date=date(2022, 1, 1), end_date=date(2025, 12, 31),
            cost=45000, monthly_cost=1250,
        ))
        db.add(Contract(
            vehicle_id=vehicles[1].id, contract_type=ContractType.purchase,
            reference="PO-2021-045", company="Ford Dealer",
            start_date=date(2021, 6, 15),
            cost=38000,
        ))

        # ── Insurance policies ───────────────────────────────────────────────
        db.add(InsurancePolicy(
            vehicle_id=vehicles[0].id, policy_number="INS-2024-TRK001",
            insurer="SafeDrive Insurance", coverage_type="Comprehensive",
            start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
            premium=1800,
        ))
        db.add(InsurancePolicy(
            vehicle_id=vehicles[1].id, policy_number="INS-2024-TRK002",
            insurer="FleetGuard Insurance", coverage_type="Third Party",
            start_date=date(2024, 3, 1), end_date=date(2024, 12, 1),
            premium=950,
        ))

        # ── Alerts ──────────────────────────────────────────────────────────
        db.add(Alert(
            vehicle_id=vehicles[1].id,
            alert_type=AlertType.insurance_expiry,
            title="Insurance Expiring Soon",
            message="Insurance for TRK-002 expires in 30 days",
            due_date=today + timedelta(days=30),
        ))
        db.add(Alert(
            vehicle_id=vehicles[5].id,
            alert_type=AlertType.maintenance_due,
            title="Urgent: Maintenance Overdue",
            message="TRK-003 engine overhaul is overdue",
            due_date=today - timedelta(days=5),
        ))

        # ── Activity log ─────────────────────────────────────────────────────
        for action, eid, etype in [
            ("create_vehicle", vehicles[0].id, "vehicle"),
            ("create_vehicle", vehicles[1].id, "vehicle"),
            ("login", admin.id, "user"),
            ("add_fuel_log", vehicles[0].id, "fuel_log"),
        ]:
            db.add(ActivityLog(
                user_id=admin.id, action=action,
                entity_type=etype, entity_id=eid,
            ))

        await db.commit()
        print("✅ Seed complete!")
        print()
        print("Demo accounts:")
        print("  admin@fleethq.com    / admin123   (Admin)")
        print("  manager@fleethq.com  / manager123 (Fleet Manager)")
        print("  jordan@fleethq.com   / driver123  (Driver)")
        print("  viewer@fleethq.com   / viewer123  (Viewer)")


if __name__ == "__main__":
    asyncio.run(seed())