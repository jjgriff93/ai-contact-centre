from typing import Dict, List


class ConversationEvaluator:
    """Evaluator for conversation turn metrics."""

    def __call__(self, *, transcription: List[str], **kwargs) -> Dict[str, float]:
        """Evaluate conversation turn metrics."""
        return {
            # Transcription lines contain "assistant" and "user" messages, both combined are 1 turn
            "total_turns": len(transcription) // 2
        }
