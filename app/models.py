from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Enum, Date, Numeric, JSON
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from app.database import Base
import enum
import uuid
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime


def gen_uuid():
    return str(uuid.uuid4())


# ─── Enums ───────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin = "admin"
    fleet_manager = "fleet_manager"
    driver = "driver"
    viewer = "viewer"


class VehicleStatus(str, enum.Enum):
    active = "active"
    in_maintenance = "in_maintenance"
    out_of_service = "out_of_service"
    reserved = "reserved"


class FuelType(str, enum.Enum):
    petrol = "petrol"
    diesel = "diesel"
    electric = "electric"
    hybrid = "hybrid"
    lpg = "lpg"
    cng = "cng"


class ContractType(str, enum.Enum):
    purchase = "purchase"
    lease = "lease"
    rental = "rental"


class MaintenanceType(str, enum.Enum):
    preventive = "preventive"
    corrective = "corrective"
    inspection = "inspection"
    tire = "tire"
    oil_change = "oil_change"
    other = "other"


class MaintenanceStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class AlertType(str, enum.Enum):
    contract_expiry = "contract_expiry"
    insurance_expiry = "insurance_expiry"
    maintenance_due = "maintenance_due"
    license_expiry = "license_expiry"
    service_due = "service_due"


# ─── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(String, primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.viewer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    department: Mapped[str] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    last_login: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)

    # Relationships
    assigned_vehicles = relationship("Vehicle", back_populates="assigned_driver", foreign_keys="Vehicle.driver_id")
    fuel_logs = relationship("FuelLog", back_populates="logged_by_user")
    maintenance_records = relationship("MaintenanceRecord", back_populates="technician")
    activity_logs = relationship("ActivityLog", back_populates="user")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(String, primary_key=True, default=gen_uuid)
    license_plate = Column(String(50), unique=True, nullable=False, index=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    year = Column(Integer, nullable=False)
    color = Column(String(50), nullable=True)
    vin = Column(String(100), unique=True, nullable=True)
    fuel_type = Column(Enum(FuelType), default=FuelType.petrol)
    status = Column(Enum(VehicleStatus), default=VehicleStatus.active)
    odometer = Column(Integer, default=0)  # in km
    seats = Column(Integer, default=5)
    tags = Column(JSON, default=list)
    notes = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # FK
    driver_id = Column(String, ForeignKey("users.id"), nullable=True)

    # Relationships
    assigned_driver = relationship("User", back_populates="assigned_vehicles", foreign_keys=[driver_id])
    contracts = relationship("Contract", back_populates="vehicle", cascade="all, delete-orphan")
    insurance_policies = relationship("InsurancePolicy", back_populates="vehicle", cascade="all, delete-orphan")
    fuel_logs = relationship("FuelLog", back_populates="vehicle", cascade="all, delete-orphan")
    maintenance_records = relationship("MaintenanceRecord", back_populates="vehicle", cascade="all, delete-orphan")
    odometer_logs = relationship("OdometerLog", back_populates="vehicle", cascade="all, delete-orphan")


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(String, primary_key=True, default=gen_uuid)
    vehicle_id = Column(String, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    contract_type = Column(Enum(ContractType), default=ContractType.purchase)
    reference = Column(String(100), nullable=True)
    company = Column(String(255), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    cost = Column(Numeric(12, 2), default=0)
    monthly_cost = Column(Numeric(12, 2), default=0)
    max_km = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    vehicle = relationship("Vehicle", back_populates="contracts")


class InsurancePolicy(Base):
    __tablename__ = "insurance_policies"

    id = Column(String, primary_key=True, default=gen_uuid)
    vehicle_id = Column(String, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    policy_number = Column(String(100), nullable=False)
    insurer = Column(String(255), nullable=False)
    coverage_type = Column(String(100), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    premium = Column(Numeric(12, 2), default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="insurance_policies")


class FuelLog(Base):
    __tablename__ = "fuel_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    vehicle_id = Column(String, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    logged_by = Column(String, ForeignKey("users.id"), nullable=True)
    date = Column(Date, nullable=False)
    liters = Column(Numeric(8, 2), nullable=False)
    cost_per_liter = Column(Numeric(8, 3), nullable=False)
    total_cost = Column(Numeric(10, 2), nullable=False)
    odometer = Column(Integer, nullable=False)
    station = Column(String(255), nullable=True)
    full_tank = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="fuel_logs")
    logged_by_user = relationship("User", back_populates="fuel_logs")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id = Column(String, primary_key=True, default=gen_uuid)
    vehicle_id = Column(String, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    technician_id = Column(String, ForeignKey("users.id"), nullable=True)
    maintenance_type = Column(Enum(MaintenanceType), default=MaintenanceType.preventive)
    status = Column(Enum(MaintenanceStatus), default=MaintenanceStatus.scheduled)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scheduled_date = Column(Date, nullable=False)
    completed_date = Column(Date, nullable=True)
    odometer_at_service = Column(Integer, nullable=True)
    cost = Column(Numeric(12, 2), default=0)
    vendor = Column(String(255), nullable=True)
    next_service_date = Column(Date, nullable=True)
    next_service_km = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    vehicle = relationship("Vehicle", back_populates="maintenance_records")
    technician = relationship("User", back_populates="maintenance_records")


class OdometerLog(Base):
    __tablename__ = "odometer_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    vehicle_id = Column(String, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    value = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="odometer_logs")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=gen_uuid)
    vehicle_id = Column(String, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=True)
    alert_type = Column(Enum(AlertType), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True)
    is_read = Column(Boolean, default=False)
    is_dismissed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    action = Column(String(255), nullable=False)
    entity_type = Column(String(100), nullable=True)
    entity_id = Column(String, nullable=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="activity_logs")