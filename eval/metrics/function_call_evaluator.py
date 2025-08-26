import logging
import sys
from dataclasses import dataclass
from typing import Dict, List


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add a console handler explicitly
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Prevent propagation to parent loggers that might be captured
logger.propagate = False


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
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        # Log details of actual calls
        if actual:
            logger.info("  - Actual function calls:")
            for fcall in actual:
                logger.info("    • %s", fcall)
        
        # Log details of expected calls not made
        missed_calls = [fcall for fcall in expected if fcall not in actual]
        if missed_calls:
            logger.info("  - Missed expected calls:")
            for fcall in missed_calls:
                logger.info("    • %s", fcall)
        
        # Log details of unexpected calls made
        unexpected_made = [fcall for fcall in actual if fcall in unexpected]
        if unexpected_made:
            logger.info("  - Unexpected calls made:")
            for fcall in unexpected_made:
                logger.info("    • %s", fcall)

        logger.info("  - Counts: actual=%d, expected=%d, unexpected=%d, matches_expected=%d, matches_unexpected=%d",
                    len(actual), len(expected), len(unexpected), nmatches_expected, nmatches_unexpected)
        logger.info("  - Metrics: precision=%.2f, recall=%.2f", precision, recall)

        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total": len(actual),
            "expected": len(expected),
            "tp": nmatches_expected,
            "fp": len(actual) - nmatches_expected,
            "fn": len(expected) - nmatches_expected,
            "faults": nmatches_unexpected
        }

    def __aggregate__(self, scores: List[Dict[str, float]]) -> Dict[str, float]:
        if not scores:
            return {
                "micro_precision": 0.0,
                "micro_recall": 0.0,
                "micro_f1": 0.0,
                "total_calls": 0,
                "total_faults": 0,
                "num_evaluations": 0
            }

        # Pool counts for micro
        TP = sum(s.get("tp", 0) for s in scores)
        FP = sum(s.get("fp", 0) for s in scores)
        FN = sum(s.get("fn", 0) for s in scores)

        micro_precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
        micro_recall    = TP / (TP + FN) if (TP + FN) > 0 else 0.0
        micro_f1 = (2 * micro_precision * micro_recall /
                    (micro_precision + micro_recall)) if (micro_precision + micro_recall) > 0 else 0.0

        return {
            "micro_precision": micro_precision,
            "micro_recall": micro_recall,
            "micro_f1": micro_f1,
            "total_calls": sum(s["total"] for s in scores),
            "total_faults": sum(s.get("faults", 0) for s in scores),
            "num_evaluations": len(scores)
        }