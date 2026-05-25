from typing import Protocol, Any, Dict, List

from typing import Protocol, Any, Dict, List

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
