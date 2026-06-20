from dataclasses import dataclass
from enum import Enum
from typing import Optional
from datetime import datetime


class HealthcareAssetType(Enum):
    PATIENT_RECORD = "patient_record"
    MEDICAL_DEVICE = "medical_device"
    CLINIC = "clinic"
    HEALTHCARE_ASSET = "healthcare_asset"


class HealthcareActionType(Enum):
    OBSERVE = "observe"
    ANALYZE = "analyze"
    RECOMMEND = "recommend"
    CONTROL_WRITE = "control_write"
    PATIENT_DATA_EXPORT = "patient_data_export"
    DEVICE_RECONFIGURATION = "device_reconfiguration"


class PatientRecordStatus(Enum):
    ACTIVE = "active"
    DISCHARGED = "discharged"
    CRITICAL = "critical"


class MedicalDeviceStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    CALIBRATION_REQUIRED = "calibration_required"


@dataclass(frozen=True)
class PatientRecord:
    record_id: str
    patient_id: str
    clinic_id: str
    status: PatientRecordStatus
    twin_asset_id: str
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()


@dataclass(frozen=True)
class MedicalDevice:
    device_id: str
    clinic_id: str
    device_type: str
    status: MedicalDeviceStatus
    twin_asset_id: str
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()


@dataclass(frozen=True)
class Clinic:
    clinic_id: str
    name: str
    capacity: int
    current_occupancy: int
    status: str
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()


@dataclass(frozen=True)
class HealthcareSafetyDecision:
    allowed: bool
    reason: str
    action_type: HealthcareActionType
    requires_approval: bool
    violation_type: Optional[str] = None