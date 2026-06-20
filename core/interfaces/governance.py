from typing import Protocol, Any, Dict, List, Optional


class IContractValidator(Protocol):
    @staticmethod
    def validate_inputs(contract: Any, inputs: Dict[str, Any]) -> List[str]:
        ...

    @staticmethod
    def validate_outputs(contract: Any, outputs: Dict[str, Any]) -> List[str]:
        ...


class IComplianceValidator(Protocol):
    @staticmethod
    def verify_frozen_methods(cls: Any) -> None:
        ...

    @staticmethod
    def validate_outputs(contract: Any, outputs: Dict[str, Any]) -> List[str]:
        ...


class IApprovalGate(Protocol):
    """Protocol for human-in-the-loop approval gating."""

    def check_and_request(
        self,
        tenant_id: str,
        org_id: Optional[str],
        action: str,
        requested_by: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate policy and request approval if needed.

        Returns:
            {
                "status": "APPROVED" | "PENDING" | "REJECTED",
                "request_id": Optional[str],
                "reason": str
            }
        """
        ...
