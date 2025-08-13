import json
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents import FunctionCallContent, FunctionResultContent


def export_chat_history(chat_history: ChatHistory, from_index: int = 0) -> str:
    """Convert chat history to JSON format.

    Args:
        chat_history: the ChatHistory object to export
        from_index: starting index to export from (default: 0, export all messages)

    Returns:
        A JSON string representation of the chat history
    """
    # Filter messages from the given index
    messages_raw = chat_history.messages[from_index:]

    # Convert messages from SK class to dict
    messages_formatted = []
    for msg in messages_raw:
        message_data = {
            "role": msg.role.value
        }

        if msg.content:
            message_data["content"] = str(msg.content)

        # Include function calls if present
        function_calls = []
        for item in msg.items:
            if isinstance(item, FunctionCallContent):
                function_calls.append({
                    "function_name": item.function_name,
                    "plugin": item.plugin_name,
                    "arguments": json.loads(item.arguments)
                })
            elif isinstance(item, FunctionResultContent):
                function_calls.append({
                    "function_name": item.function_name,
                    "plugin": item.plugin_name,
                    "arguments_sent": item.metadata["arguments"],
                    "arguments_used": item.metadata["used_arguments"],
                    "result": item.result
                })

        if function_calls:
            message_data["function_calls"] = function_calls

        messages_formatted.append(message_data)

    return messages_formatted
