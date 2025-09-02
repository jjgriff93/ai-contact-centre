from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ConversationMetrics:
    total_turns: int = None


class ConversationEvaluator:
    """Evaluator for conversation turn metrics."""

    def __call__(self, *, conversation: Dict[str, List[Dict]], **kwargs) -> Dict[str, float]:
        """Evaluate conversation turn metrics.
        Conversation in the format expected by Azure Evaluators:
        https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/evaluate-sdk#conversation-support-for-text
        """

        if conversation is None:  # Failed run - no outputs to evaluate
            return ConversationMetrics()

        return ConversationMetrics(
            total_turns=len(conversation["messages"]) // 2
        )
