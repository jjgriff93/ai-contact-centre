from typing import Dict, List


class ConversationEvaluator:
    """Evaluator for conversation turn metrics."""

    def __call__(self, *, conversation: Dict[str, List[Dict]], **kwargs) -> Dict[str, float]:
        """Evaluate conversation turn metrics.
        Conversation in the format expected by Azure Evaluators:
        https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/evaluate-sdk#conversation-support-for-text
        """

        return {
            # Conversation lines contain "assistant" and "user" messages, both combined are 1 turn
            "total_turns": len(conversation["messages"]) // 2
        }
