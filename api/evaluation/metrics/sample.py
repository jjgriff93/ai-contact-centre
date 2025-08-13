from typing import Dict, List


class FunctionCallEvaluator:
    """Evaluator for checking expected and unexpected function calls."""

    def __init__(self, expected_calls: List[Dict[str, object]] = None,
                 unexpected_calls: List[Dict[str, object]] = None):
        self.expected_calls = expected_calls or []
        self.unexpected_calls = unexpected_calls or []

    def __call__(self, *, function_calls: List[Dict[str, object]], **kwargs) -> Dict[str, object]:
        """Evaluate function calls against expected and unexpected patterns."""
        expected_score = 0
        unexpected_score = 0

        # Check for expected function calls
        if self.expected_calls:
            for expected in self.expected_calls:
                found = any(
                    call.get("pluginName") == expected.get("pluginName") and
                    call.get("functionName") == expected.get("functionName")
                    for call in function_calls
                )
                if found:
                    expected_score += 1

            expected_score = expected_score / len(self.expected_calls)

        # Check for unexpected function calls
        if self.unexpected_calls:
            for unexpected in self.unexpected_calls:
                found = any(
                    call.get("pluginName") == unexpected.get("pluginName") and
                    call.get("functionName") == unexpected.get("functionName")
                    for call in function_calls
                )
                if found:
                    unexpected_score += 1

        return {
            "expected_function_calls_score": expected_score,
            "unexpected_function_calls_found": unexpected_score,
            "total_function_calls": len(function_calls)
        }


class ConversationTurnsEvaluator:
    """Evaluator for conversation turn metrics."""

    def __call__(self, *, transcription: List[str], **kwargs) -> Dict[str, float]:
        """Evaluate conversation turn metrics."""
        return {
            # Transcription lines contain "assistant" and "user" messages in turns
            "conversation_turns": len(transcription) // 2
        }
