import pytest
from dataclasses import FrozenInstanceError
from core.models.healthcare import (
    HealthcareAssetType,
    HealthcareActionType,
    PatientRecordStatus,
    MedicalDeviceStatus,
    PatientRecord,
    MedicalDevice,
    Clinic,
    HealthcareSafetyDecision,
)
from core.governance.healthcare_policies import (
    HealthcarePolicyType,
    evaluate_policy,
    DEFAULT_HEALTHCARE_POLICIES,
    CONTROL_WRITE_ACTIONS,
)


def test_healthcare_models_are_frozen():
    record = PatientRecord(
        record_id="rec-001",
        patient_id="pat-001",
        clinic_id="clinic-001",
        status=PatientRecordStatus.ACTIVE,
        twin_asset_id="twin-001",
    )
    with pytest.raises(FrozenInstanceError):
        record.status = PatientRecordStatus.DISCHARGED
    
    device = MedicalDevice(
        device_id="dev-001",
        clinic_id="clinic-001",
        device_type="ventilator",
        status=MedicalDeviceStatus.ONLINE,
        twin_asset_id="twin-002",
    )
    with pytest.raises(FrozenInstanceError):
        device.status = MedicalDeviceStatus.OFFLINE
    
    clinic = Clinic(
        clinic_id="clinic-001",
        name="Test Clinic",
        capacity=100,
        current_occupancy=50,
        status="active",
    )
    with pytest.raises(FrozenInstanceError):
        clinic.current_occupancy = 75


def test_hipaa_denies_patient_data_export_by_default():
    decision = evaluate_policy(HealthcareActionType.PATIENT_DATA_EXPORT, trust_level="UNTRUSTED")
    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.violation_type == "UNAUTHORIZED_CONTROL_WRITE"
    assert "TRUSTED approval" in decision.reason


def test_device_reconfiguration_requires_trusted_approval():
    decision = evaluate_policy(HealthcareActionType.DEVICE_RECONFIGURATION, trust_level="UNTRUSTED")
    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.violation_type == "UNAUTHORIZED_CONTROL_WRITE"
    
    decision_trusted = evaluate_policy(HealthcareActionType.DEVICE_RECONFIGURATION, trust_level="TRUSTED")
    assert decision_trusted.allowed is True
    assert decision_trusted.requires_approval is True
    assert decision_trusted.violation_type is None


def test_patient_record_read_only_integrity():
    record = PatientRecord(
        record_id="rec-001",
        patient_id="pat-001",
        clinic_id="clinic-001",
        status=PatientRecordStatus.ACTIVE,
        twin_asset_id="twin-001",
    )
    assert record.record_id == "rec-001"
    assert record.patient_id == "pat-001"
    assert record.clinic_id == "clinic-001"
    assert record.status == PatientRecordStatus.ACTIVE
    assert record.twin_asset_id == "twin-001"
    assert isinstance(record.created_at, type(record.updated_at))


def test_unknown_action_default_deny():
    unknown_action = HealthcareActionType.OBSERVE
    decision = evaluate_policy(unknown_action, trust_level="UNTRUSTED")
    assert decision.allowed is True
    assert decision.requires_approval is False
    assert decision.violation_type is None


def test_policy_evaluation_blocks_unauthorized_device_reconfiguration():
    for action in CONTROL_WRITE_ACTIONS:
        decision = evaluate_policy(action, trust_level="UNTRUSTED")
        assert decision.allowed is False, f"Action {action.value} should be denied for UNTRUSTED"
        assert decision.requires_approval is True
        assert decision.violation_type == "UNAUTHORIZED_CONTROL_WRITE"
    
    for action in CONTROL_WRITE_ACTIONS:
        decision = evaluate_policy(action, trust_level="TRUSTED")
        assert decision.allowed is True, f"Action {action.value} should be allowed for TRUSTED"
        assert decision.requires_approval is True
        assert decision.violation_type is None