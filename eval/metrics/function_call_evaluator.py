from dataclasses import dataclass
from typing import Dict, List


@dataclass
class FunctionCall:
    plugin: str
    name: str
    arguments: dict[str, str]

    @staticmethod
    def from_dict(source: Dict) -> "FunctionCall":
        """
        Converts a dictionary to a FunctionCall object.
        """
        return FunctionCall(
            plugin=source["plugin"],
            name=source["function_name"],
            arguments=source.get("arguments", None) or source.get("arguments_used", None)
        )

    def __eq__(self, value: "FunctionCall"):
        if not isinstance(value, FunctionCall):
            return NotImplemented

        # If arguments are not set for any of the 2 we just compare plugin and function name
        # For example: we want to check that schedule_delivery() has been called but we don't care which slot was chosen
        is_equal = (self.plugin == value.plugin) and (self.name == value.name)
        if self.arguments is not None and value.arguments is not None:
            is_equal = is_equal and (self.arguments == value.arguments)

        return is_equal

    def __str__(self):
        args_str = ", ".join(f"{k}={v}" for k, v in (self.arguments or {}).items())
        return f"{self.plugin}.{self.name}({args_str})"


@dataclass
class FunctionCallMetrics:
    precision: float = None
    recall: float = None
    f1: float = None
    total: int = None
    faults: int = None


class FunctionCallEvaluator:
    """
    An evaluator to calculate function call metrics.
        - Precision = Number of correct function_calls / Actual number of function_calls
        - Recall = Number of correct function_calls / Expected number of function_calls
        - F1 = geometric mean between precision and recall
    """

    def __call__(self, *, function_calls: List[Dict],
                 expected_function_calls: List[Dict], unexpected_function_calls: List[Dict],
                 **kwargs) -> Dict[str, float]:

        if function_calls is None:  # Failed run - no outputs to evaluate
            return FunctionCallMetrics()

        # Convert the dicts to FunctionCall objects for easier handling
        actual = [FunctionCall.from_dict(fcall) for fcall in function_calls]
        expected = [FunctionCall.from_dict(fcall) for fcall in expected_function_calls]
        unexpected = [FunctionCall.from_dict(fcall) for fcall in unexpected_function_calls]

        if any(fcall in unexpected for fcall in expected) or any(fcall in expected for fcall in unexpected):
            raise ValueError("Error in data: expected and unexpected function calls are not disjoint.")

        nmatches_expected = sum(1 for fcall in actual if fcall in expected)
        nmatches_unexpected = sum(1 for fcall in actual if fcall in unexpected)

        precision = nmatches_expected / len(actual) if actual else 0
        recall = nmatches_expected / len(expected) if expected else 0

        return FunctionCallMetrics(
            precision=precision,
            recall=recall,
            f1=2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0,
            total=len(actual),
            faults=nmatches_unexpected
        )

    # def __aggregate__(self, input):
    #     pass  #TODO
