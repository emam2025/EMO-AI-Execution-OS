"""CanaryConfig — 3 isolated users with bounded resources and tracing."""

# LAW-5: Observable — every canary user has tracing_flags enabled
# LAW-11: No Global State — each user has isolated repo + dedicated worker pool
# LAW-12: Traceable — every operation carries canary_trace_id

import dataclasses
from typing import Dict, List


@dataclasses.dataclass(frozen=True)
class ResourceLimits:
    cpu_cores: float
    memory_mb: int
    max_concurrent_dags: int
    max_retries: int
    timeout_sec: int


@dataclasses.dataclass(frozen=True)
class TracingFlags:
    capture_spans: bool = True
    capture_metrics: bool = True
    capture_replay: bool = True
    capture_memory: bool = True


@dataclasses.dataclass(frozen=True)
class CanaryUser:
    user_id: str
    isolated_repo_path: str
    resource_limits: ResourceLimits
    tracing_flags: TracingFlags
    worker_pool_label: str
    max_session_duration_sec: int = 3600


@dataclasses.dataclass(frozen=True)
class CanaryConfig:
    users: List[CanaryUser]
    strict_canary_mode: bool = True
    metrics_collection_interval_sec: int = 10
    anomaly_check_interval_sec: int = 30
    f4_observability_topic: str = "runtime.canary.metrics"
    j3_readiness_topic: str = "runtime.readiness.canary"
    rollback_on_breach: bool = True

    @property
    def user_map(self) -> Dict[str, CanaryUser]:
        return {u.user_id: u for u in self.users}


DEFAULT_CANARY_CONFIG = CanaryConfig(
    users=[
        CanaryUser(
            user_id="user-alpha",
            isolated_repo_path="/tmp/canary/repos/alpha/",
            resource_limits=ResourceLimits(
                cpu_cores=1.0,
                memory_mb=512,
                max_concurrent_dags=5,
                max_retries=3,
                timeout_sec=300,
            ),
            tracing_flags=TracingFlags(),
            worker_pool_label="pool-alpha",
        ),
        CanaryUser(
            user_id="user-beta",
            isolated_repo_path="/tmp/canary/repos/beta/",
            resource_limits=ResourceLimits(
                cpu_cores=2.0,
                memory_mb=1024,
                max_concurrent_dags=10,
                max_retries=3,
                timeout_sec=600,
            ),
            tracing_flags=TracingFlags(),
            worker_pool_label="pool-beta",
        ),
        CanaryUser(
            user_id="user-gamma",
            isolated_repo_path="/tmp/canary/repos/gamma/",
            resource_limits=ResourceLimits(
                cpu_cores=0.5,
                memory_mb=256,
                max_concurrent_dags=3,
                max_retries=5,
                timeout_sec=180,
            ),
            tracing_flags=TracingFlags(),
            worker_pool_label="pool-gamma",
        ),
    ],
    strict_canary_mode=True,
)
