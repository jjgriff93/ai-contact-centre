from typing import Dict, List


class ConversationEvaluator:
    """Evaluator for conversation turn metrics."""

    def __call__(self, *, conversation: Dict[str, List[Dict]], transcription: List[Dict] = None, **kwargs) -> Dict[str, float]:
        """Evaluate conversation turn metrics.
        Conversation in the format expected by Azure Evaluators:
        https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/evaluate-sdk#conversation-support-for-text
        
        Args:
            conversation: Dict with 'messages' list containing role and content
            transcription: List of message dicts with timing information
        """
        
        metrics = {
            # Conversation lines contain "assistant" and "user" messages, both combined are 1 turn
            "total_turns": len(conversation["messages"]) // 2,
            "call_handling_time_seconds": 0.0
        }
        
        # Calculate call handling time from transcription if available
        if transcription and len(transcription) > 0:
            # Find first and last message timestamps
            first_msg = transcription[0]
            last_msg = transcription[-1]
            
            # Use start_datetime/end_datetime if available, otherwise use datetime
            if "start_datetime" in first_msg and "end_datetime" in last_msg:
                # Parse ISO datetime strings to calculate duration
                from datetime import datetime
                start_time = datetime.fromisoformat(first_msg["start_datetime"])
                end_time = datetime.fromisoformat(last_msg["end_datetime"])
                duration = (end_time - start_time).total_seconds()
                metrics["call_handling_time_seconds"] = duration
            elif "duration_seconds" in last_msg:
                # Sum up all durations if available
                total_duration = sum(msg.get("duration_seconds", 0) for msg in transcription if msg.get("duration_seconds"))
                metrics["call_handling_time_seconds"] = total_duration
        
        return metrics
    