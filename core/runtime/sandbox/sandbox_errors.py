"""Phase 4.1.4 — SandboxErrors: custom exceptions for sandbox isolation."""


class SandboxError(Exception):
    """Base exception for all sandbox errors."""

    def __init__(self, message: str, sandbox_id: str = ""):
        self.sandbox_id = sandbox_id
        super().__init__(message)


class SandboxViolationError(SandboxError):
    """Raised when a sandbox violates security rules."""

    def __init__(self, message: str, sandbox_id: str = ""):
        super().__init__(f"Sandbox violation: {message}", sandbox_id)


class ResourceLimitExceeded(SandboxError):
    """Raised when an execution exceeds its resource limits."""

    def __init__(
        self,
        resource: str = "",
        limit: float = 0.0,
        actual: float = 0.0,
        sandbox_id: str = "",
    ):
        msg = f"Resource limit exceeded: {resource} (limit={limit}, actual={actual})"
        self.resource = resource
        self.limit = limit
        self.actual = actual
        super().__init__(msg, sandbox_id)


class ExecutionTimeoutError(SandboxError):
    """Raised when an execution exceeds its timeout."""

    def __init__(
        self,
        tool: str = "",
        timeout: float = 0.0,
        elapsed: float = 0.0,
        sandbox_id: str = "",
    ):
        msg = f"Execution timed out: {tool} (timeout={timeout}s, elapsed={elapsed:.2f}s)"
        self.tool = tool
        self.timeout = timeout
        self.elapsed = elapsed
        super().__init__(msg, sandbox_id)
