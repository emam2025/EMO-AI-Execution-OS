"""Remote Capability Negotiation — worker ↔ engine compatibility protocol.

Architecture:
    Worker advertises:
        tools: [{name, version, contract_version, ...}]
        contracts: [{name, inputs, outputs, ...}]
        schema_versions: ["1.0.0", ...]
        runtime_version: "1.0.0"

    Engine validates:
        1. Schema version compatibility
        2. Tool availability (name + version)
        3. Contract compatibility
        4. Runtime version compatibility

    Result:
        CapabilityReport: {compatible, reasons, warnings}

Usage:
    negotiator = CapabilityNegotiator()
    report = negotiator.validate(worker_capabilities)
    if report.compatible:
        engine.register_worker(url, report)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .contracts import SUPPORTED_SCHEMA_VERSIONS, DAG_SCHEMA_VERSION, ToolContract

logger = logging.getLogger("emo_ai.capability_negotiation")

CAPABILITY_NEGOTIATION_VERSION = "1.0.0"
ENGINE_RUNTIME_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════


@dataclass
class WorkerCapability:
    """Capabilities advertised by a remote worker node."""
    tools: List[Dict[str, Any]]
    contracts: List[Dict[str, Any]]
    schema_versions: List[str]
    runtime_version: str = "0.0.0"
    worker_id: str = ""
    url: str = ""
    capacity: int = 1
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class CapabilityReport:
    """Result of validating a worker's capabilities against the engine."""
    compatible: bool
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Per-category details
    schema_compatible: bool = True
    tools_compatible: bool = True
    contracts_compatible: bool = True
    runtime_compatible: bool = True

    # Parsed worker info
    worker_id: str = ""
    supported_tools: List[str] = field(default_factory=list)
    supported_versions: Set[str] = field(default_factory=set)

    def merge(self, other: CapabilityReport) -> CapabilityReport:
        self.compatible = self.compatible and other.compatible
        self.reasons.extend(other.reasons)
        self.warnings.extend(other.warnings)
        self.schema_compatible = self.schema_compatible and other.schema_compatible
        self.tools_compatible = self.tools_compatible and other.tools_compatible
        self.contracts_compatible = self.contracts_compatible and other.contracts_compatible
        self.runtime_compatible = self.runtime_compatible and other.runtime_compatible
        return self


# ═══════════════════════════════════════════════════════════════════
# Negotiator
# ═══════════════════════════════════════════════════════════════════


class CapabilityNegotiator:
    """Validates worker capabilities against engine requirements.

    Thread-safe (stateless).
    """

    def __init__(
        self,
        supported_schema_versions: Optional[Set[str]] = None,
        required_tools: Optional[List[str]] = None,
        min_runtime_version: str = "1.0.0",
    ):
        self._schema_versions = supported_schema_versions or SUPPORTED_SCHEMA_VERSIONS
        self._engine_version = DAG_SCHEMA_VERSION
        self._required_tools = required_tools or []
        self._min_runtime_version = min_runtime_version

    @property
    def version(self) -> str:
        return CAPABILITY_NEGOTIATION_VERSION

    # ── Core validation ─────────────────────────────────────────

    def validate(
        self,
        capabilities: WorkerCapability,
    ) -> CapabilityReport:
        """Run all compatibility checks against a worker's capabilities.

        Returns a CapabilityReport with compatible=True iff all
        required checks pass.
        """
        report = CapabilityReport(compatible=True)

        report.merge(self._check_schema(capabilities))
        report.merge(self._check_tools(capabilities))
        report.merge(self._check_contracts(capabilities))
        report.merge(self._check_runtime(capabilities))

        report.worker_id = capabilities.worker_id
        report.supported_tools = [
            t.get("name", "unknown") for t in capabilities.tools
        ]
        report.supported_versions = set(capabilities.schema_versions)

        report.compatible = (
            report.schema_compatible
            and report.tools_compatible
            and report.contracts_compatible
            and report.runtime_compatible
        )
        return report

    # ── Per-category checks ─────────────────────────────────────

    def _check_schema(
        self, capabilities: WorkerCapability,
    ) -> CapabilityReport:
        """Check DAG schema version compatibility."""
        r = CapabilityReport(compatible=True, schema_compatible=True)
        worker_versions = set(capabilities.schema_versions)

        if not worker_versions:
            r.compatible = False
            r.schema_compatible = False
            r.reasons.append(
                "Worker advertises no schema versions"
            )
            return r

        # Check that at least one worker version matches the engine
        common = worker_versions & self._schema_versions
        if not common:
            r.compatible = False
            r.schema_compatible = False
            r.reasons.append(
                f"Worker schema versions {sorted(worker_versions)} "
                f"do not overlap with engine versions "
                f"{sorted(self._schema_versions)}"
            )
            return r

        r.reasons.append(
            f"Schema version compatible: {sorted(common)[0]}"
        )
        return r

    def _check_tools(
        self, capabilities: WorkerCapability,
    ) -> CapabilityReport:
        """Check that required tools are available on the worker."""
        r = CapabilityReport(compatible=True, tools_compatible=True)
        worker_tools = {t.get("name") for t in capabilities.tools}

        for required in self._required_tools:
            if required not in worker_tools:
                r.compatible = False
                r.tools_compatible = False
                r.reasons.append(
                    f"Required tool '{required}' not available on worker"
                )
            else:
                r.reasons.append(f"Required tool '{required}' available")

        # Check for tools that worker has but engine doesn't require
        extra = worker_tools - set(self._required_tools)
        if extra:
            r.warnings.append(
                f"Worker advertises unrequired tools: {sorted(extra)}"
            )

        return r

    def _check_contracts(
        self, capabilities: WorkerCapability,
    ) -> CapabilityReport:
        """Check that advertised contracts are well-formed."""
        r = CapabilityReport(compatible=True, contracts_compatible=True)

        for contract in capabilities.contracts:
            name = contract.get("name", "unknown")
            inputs = contract.get("inputs", {})
            outputs = contract.get("outputs", {})

            if not isinstance(inputs, dict):
                r.compatible = False
                r.contracts_compatible = False
                r.reasons.append(
                    f"Contract '{name}': inputs must be a dict, "
                    f"got {type(inputs).__name__}"
                )
            if not isinstance(outputs, dict):
                r.compatible = False
                r.contracts_compatible = False
                r.reasons.append(
                    f"Contract '{name}': outputs must be a dict, "
                    f"got {type(outputs).__name__}"
                )

        if r.contracts_compatible:
            r.reasons.append(
                f"All {len(capabilities.contracts)} contracts well-formed"
            )

        return r

    def _check_runtime(
        self, capabilities: WorkerCapability,
    ) -> CapabilityReport:
        """Check runtime version meets minimum."""
        r = CapabilityReport(compatible=True, runtime_compatible=True)
        worker_ver = capabilities.runtime_version

        if worker_ver < self._min_runtime_version:
            r.compatible = False
            r.runtime_compatible = False
            r.reasons.append(
                f"Worker runtime v{worker_ver} < minimum v{self._min_runtime_version}"
            )
        else:
            r.reasons.append(
                f"Runtime v{worker_ver} meets minimum v{self._min_runtime_version}"
            )

        return r

    # ── Worker registration helper ──────────────────────────────

    def register_if_compatible(
        self,
        capabilities: WorkerCapability,
        registry,
    ) -> CapabilityReport:
        """Validate and, if compatible, register the worker.

        Args:
            capabilities: Worker's advertised capabilities.
            registry: WorkerRegistry instance.

        Returns:
            CapabilityReport with registration result.
        """
        from .distributed_types import WorkerNode, WorkerStatus
        from .models.dag import ToolSpec

        report = self.validate(capabilities)

        if not report.compatible:
            logger.warning(
                "Worker %s rejected: %s",
                capabilities.worker_id, "; ".join(report.reasons),
            )
            return report

        tool_specs = []
        for t in capabilities.tools:
            spec = ToolSpec(
                name=t.get("name", ""),
                description=t.get("description", ""),
                timeout_seconds=t.get("timeout_seconds", 30.0),
            )
            tool_specs.append(spec)

        worker = WorkerNode(
            id=capabilities.worker_id,
            url=capabilities.url,
            status=WorkerStatus.IDLE,
            tools=tool_specs,
            capacity=capabilities.capacity,
            tags=capabilities.tags,
        )
        registry.register(worker)
        logger.info(
            "Worker %s registered (tools=%d, versions=%s)",
            capabilities.worker_id,
            len(capabilities.tools),
            sorted(capabilities.schema_versions),
        )
        return report
