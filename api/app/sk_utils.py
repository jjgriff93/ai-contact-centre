import json
import logging
from pathlib import Path

import yaml
from azure.identity.aio import (DefaultAzureCredential,
                                get_bearer_token_provider)
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.contents import (ChatHistory, FunctionCallContent,
                                      FunctionResultContent)
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import (KernelPromptTemplate,
                                             PromptTemplateConfig)

from .azure_voice_live import (AzureVoiceLiveExecutionSettings,
                               AzureVoiceLiveInputAudioEchoCancellation,
                               AzureVoiceLiveInputAudioNoiseReduction,
                               AzureVoiceLiveTurnDetection,
                               AzureVoiceLiveVoiceConfig,
                               AzureVoiceLiveWebsocket)
from .config import settings

logger = logging.getLogger(__name__)


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
                    "name": item.function_name,
                    "plugin": item.plugin_name,
                    "arguments": json.loads(item.arguments)
                })
            elif isinstance(item, FunctionResultContent):
                function_calls.append({
                    "name": item.function_name,
                    "plugin": item.plugin_name,
                    "arguments_sent": item.metadata["arguments"],
                    "arguments_used": item.metadata["used_arguments"],
                    "result": item.result
                })

        if function_calls:
            message_data["function_calls"] = function_calls

        messages_formatted.append(message_data)

    return messages_formatted


async def get_agent(template_name: str, plugins: list[object], chat_history: ChatHistory, **kwargs) -> AzureVoiceLiveWebsocket:
    """
    Get a realtime voice agent by rendering a prompt template and adding plugins.

    Args:
        template_name: The name of the prompt template to use for the agent (in the templates directory).
        plugins: A list of plugins to add to the agent.
        chat_history: The chat history object to use for the agent.
        **kwargs: Additional keyword arguments to pass to the prompt template rendering.
    """
    yaml_path = Path(__file__).parent / "templates" / f"{template_name}.yaml"
    with open(yaml_path, "r") as file:
        yaml_content = file.read()
        yaml_data = yaml.safe_load(yaml_content)
    
    prompt_template_config = PromptTemplateConfig(**yaml_data)
    prompt_template = KernelPromptTemplate(prompt_template_config=prompt_template_config)
    prompt_arguments = KernelArguments(**kwargs)
    rendered_prompt = await prompt_template.render(realtime_agent._kernel, prompt_arguments) # type: ignore

    logger.debug(f"Rendered prompt: {rendered_prompt}")

    execution_settings = AzureVoiceLiveExecutionSettings(
        instructions=rendered_prompt,
        voice=AzureVoiceLiveVoiceConfig(
            name="en-US-Andrew:DragonHDLatestNeural", # en-US-Alloy:DragonHDLatestNeural, en-GB-OllieMultilingualNeural
            type="azure-standard",
        ),
        turn_detection=AzureVoiceLiveTurnDetection(
            type="server_vad",
            create_response=True,
            silence_duration_ms=800,
            threshold=0.8,
        ),
        input_audio_noise_reduction=AzureVoiceLiveInputAudioNoiseReduction(
            type="azure_deep_noise_suppression"
        ),
        input_audio_echo_cancellation=AzureVoiceLiveInputAudioEchoCancellation(
            type="server_echo_cancellation"
        ),
        # input_audio_transcription=AzureVoiceLiveInputAudioTranscription(
        #     model="azure-fast-transcription"
        # ),
        function_choice_behavior=FunctionChoiceBehavior.Auto(),
    )

    chat_history.add_system_message(execution_settings.instructions)

    return AzureVoiceLiveWebsocket(
        endpoint=settings.AZURE_AI_SERVICES_ENDPOINT, # type: ignore
        deployment_name="gpt-4o-realtime-preview",
        ad_token_provider=get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        ),
        api_version="2025-05-01-preview",
        plugins=plugins,
        settings=execution_settings
    )
