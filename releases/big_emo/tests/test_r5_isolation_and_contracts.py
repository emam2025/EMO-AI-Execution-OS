'''
Big EMO — Self-Governance Protocol Interface Tests.

15 tests across 3 groups:
  TestZeroR1R2R3R4Dependency (5) — no imports from archived releases
  TestProtocolIntegrity (5)       — protocol signatures and model validation
  TestTenantAndSeverityIsolation (5) — tenant_id + severity mandatory enforcement

Zero operational dependencies. No execution logic tested.
'''

import importlib
import pytest
import sys


def _can_import_big_emo(module_name: str) -> bool:
    try:
        importlib.import_module(f'releases.big_emo.{module_name}')
        return True
    except (ImportError, ModuleNotFoundError):
        return False


# ── TestZeroR1R2R3R4Dependency ──────────────────────────────────

class TestZeroR1R2R3R4Dependency:
    def test_cannot_import_runtime_os(self):
        assert not _can_import_big_emo('core.runtime'), 'R1 import blocked'

    def test_cannot_import_memory_os(self):
        assert not _can_import_big_emo('core.memory'), 'R2 import blocked'

    def test_cannot_import_skill_os(self):
        assert not _can_import_big_emo('core.skills'), 'R3 import blocked'

    def test_cannot_import_cognitive_os(self):
        assert not _can_import_big_emo('core.cognitive'), 'R4 import blocked'

    def test_big_emo_interfaces_importable(self):
        try:
            from releases.big_emo.core.interfaces.self_governance.ISelfBuilder import ISelfBuilder
            from releases.big_emo.core.interfaces.self_governance.ISelfHealer import ISelfHealer
            from releases.big_emo.core.interfaces.self_governance.IMultiAgentSociety import IMultiAgentSociety
            assert True
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f'Interface import failed: {e}')


# ── TestProtocolIntegrity ─────────────────────────────────────

class TestProtocolIntegrity:
    def test_self_builder_has_required_methods(self):
        from releases.big_emo.core.interfaces.self_governance.ISelfBuilder import ISelfBuilder
        methods = ['propose_tool', 'validate_sandbox']
        for m in methods:
            assert hasattr(ISelfBuilder, m), f'ISelfBuilder missing {m}()'

    def test_self_healer_has_required_methods(self):
        from releases.big_emo.core.interfaces.self_governance.ISelfHealer import ISelfHealer
        methods = ['detect_anomaly', 'apply_correction']
        for m in methods:
            assert hasattr(ISelfHealer, m), f'ISelfHealer missing {m}()'

    def test_multi_agent_society_has_required_methods(self):
        from releases.big_emo.core.interfaces.self_governance.IMultiAgentSociety import IMultiAgentSociety
        methods = ['negotiate_task', 'coordinate_swarm']
        for m in methods:
            assert hasattr(IMultiAgentSociety, m), f'IMultiAgentSociety missing {m}()'

    def test_self_build_proposal_requires_tenant_id(self):
        from releases.big_emo.core.models.self_governance import SelfBuildProposal
        with pytest.raises(ValueError, match='tenant_id'):
            SelfBuildProposal(proposal_id='p1', tenant_id='', intent='build tool')

    def test_recovery_action_requires_validator_signature(self):
        from releases.big_emo.core.models.self_governance import RecoveryAction
        with pytest.raises(ValueError, match='validator_signature'):
            RecoveryAction(action_id='a1', tenant_id='t1', target_service='svc', validator_signature='')


# ── TestTenantAndSeverityIsolation ────────────────────────────

class TestTenantAndSeverityIsolation:
    def test_anomaly_report_requires_tenant_id(self):
        from releases.big_emo.core.models.self_governance import AnomalyReport
        with pytest.raises(ValueError, match='tenant_id'):
            AnomalyReport(report_id='r1', tenant_id='', source_service='svc')

    def test_swarm_allocation_requires_tenant_id(self):
        from releases.big_emo.core.models.self_governance import SwarmAllocation
        with pytest.raises(ValueError, match='tenant_id'):
            SwarmAllocation(allocation_id='a1', tenant_id='', task_id='t1')

    def test_risk_score_bounds(self):
        from releases.big_emo.core.models.self_governance import SelfBuildProposal
        with pytest.raises(ValueError, match='risk_score'):
            SelfBuildProposal(proposal_id='p1', tenant_id='t1', intent='test', risk_score=1.5)

    def test_anomaly_severity_default_medium(self):
        from releases.big_emo.core.models.self_governance import AnomalyReport, AnomalySeverity
        r = AnomalyReport(report_id='r1', tenant_id='t1', source_service='svc')
        assert r.severity == AnomalySeverity.MEDIUM

    def test_self_build_proposal_valid_creation(self):
        from releases.big_emo.core.models.self_governance import SelfBuildProposal, ProposalStatus
        p = SelfBuildProposal(proposal_id='p1', tenant_id='t1', intent='create analyser', risk_score=0.3)
        assert p.status == ProposalStatus.DRAFT
        assert p.risk_score == 0.3
