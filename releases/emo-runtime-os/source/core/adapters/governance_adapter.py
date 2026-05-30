from typing import Any, Dict, List
from ..interfaces.governance import IContractValidator, IComplianceValidator
from ..contracts import ContractValidator
from ..api_compliance import verify_frozen_methods

class DefaultContractValidator:
    """Adapter for the legacy ContractValidator class."""
    @staticmethod
    def validate_inputs(contract: Any, inputs: Dict[str, Any]) -> List[str]:
        return ContractValidator.validate_inputs(contract, inputs)

    @staticmethod
    def validate_outputs(contract: Any, outputs: Dict[str, Any]) -> List[str]:
        return ContractValidator.validate_outputs(contract, outputs)

class DefaultComplianceValidator:
    """Adapter for the legacy verify_frozen_methods function."""
    @staticmethod
    def verify_frozen_methods(cls: Any) -> None:
        verify_frozen_methods(cls)
