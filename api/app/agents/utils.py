import base64
import json
import logging
from pathlib import Path
from typing import Any

import yaml
from azure.identity.aio import (DefaultAzureCredential,
                                get_bearer_token_provider)
from fastapi import WebSocket
from numpy import ndarray
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import (AzureRealtimeWebsocket,
                                                   ListenEvents, SendEvents)
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_realtime_execution_settings import \
    AzureRealtimeExecutionSettings
from semantic_kernel.connectors.ai.realtime_client_base import \
    RealtimeClientBase
from semantic_kernel.contents import (ChatHistory, FunctionCallContent,
                                      FunctionResultContent)
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import (KernelPromptTemplate,
                                             PromptTemplateConfig)

from ..config import settings
from .azure_voice_live import (AzureVoiceLiveExecutionSettings,
                               AzureVoiceLiveWebsocket)

logger = logging.getLogger(__name__)


def export_chat_history(chat_history: ChatHistory, from_index: int = 0) -> list[dict[str, Any]]:
    """Convert chat history to a list of dicts suitable for JSON serialization."""
    messages_raw = chat_history.messages[from_index:]

    messages_formatted: list[dict[str, Any]] = []
    for msg in messages_raw:
        message_data: dict[str, Any] = {"role": msg.role.value}
        if msg.content:
            message_data["content"] = str(msg.content)

        function_calls: list[dict[str, Any]] = []
        for item in msg.items:
            if isinstance(item, FunctionCallContent):
                parsed_args: dict | list | str | None
                if isinstance(item.arguments, str):
                    try:
                        parsed_args = json.loads(item.arguments)
                    except Exception:
                        parsed_args = item.arguments
                elif isinstance(item.arguments, dict):
                    parsed_args = item.arguments
                else:
                    parsed_args = None

                function_calls.append(
                    {
                        "name": item.function_name,
                        "plugin": item.plugin_name,
                        "arguments": parsed_args,
                    }
                )
            elif isinstance(item, FunctionResultContent):
                function_calls.append(
                    {
                        "name": item.function_name,
                        "plugin": item.plugin_name,
                        "arguments_sent": item.metadata["arguments"],
                        "arguments_used": item.metadata["used_arguments"],
                        "result": item.result,
                    }
                )

        if function_calls:
            message_data["function_calls"] = function_calls

        messages_formatted.append(message_data)

    return messages_formatted


async def get_agent(template_name: str, plugins: list[object], chat_history: ChatHistory, **kwargs) -> AzureRealtimeWebsocket:
    """
    Get a realtime voice agent by rendering a prompt template and adding plugins.

    Args:
        template_name: The name of the prompt template to use for the agent (in the prompts directory).
        plugins: A list of plugins to add to the agent.
        chat_history: The chat history object to use for the agent.
        **kwargs: Additional keyword arguments to pass to the prompt template rendering.
    """
    yaml_path = Path(__file__).parent / "prompts" / f"{template_name}.yaml"
    with open(yaml_path, "r") as file:
        yaml_content = file.read()
        yaml_data = yaml.safe_load(yaml_content)
    
    prompt_template_config = PromptTemplateConfig(**yaml_data)
    prompt_template = KernelPromptTemplate(prompt_template_config=prompt_template_config)
    prompt_arguments = KernelArguments(**kwargs)

    rendered_prompt = await prompt_template.render(Kernel(), prompt_arguments)
    logger.debug(f"Rendered prompt: {rendered_prompt}")

    # Load voice live execution settings from a single YAML file (env override supported)
    config_path = str(Path(__file__).parent / "settings" / settings.REALTIME_CONFIG_PATH)
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    # Determine service mode from config
    service = cfg.pop("service", None).lower()
    deployment_name = cfg.pop("deployment_name", None) or "gpt-4o-realtime-preview"
    api_version = cfg.pop("api_version", None) or "2025-05-01-preview"

    # Prepare execution settings payload
    exec_payload = dict(cfg)

    # Merge rendered instructions, taking precedence over YAML if provided via template
    # YAML may include an instructions placeholder; always override with rendered prompt when present
    exec_payload["instructions"] = rendered_prompt

    # Construct pydantic settings allowing nested dicts to be parsed into models
    if service == "azure_realtime":
        execution_settings = AzureRealtimeExecutionSettings(
            function_choice_behavior=FunctionChoiceBehavior.Auto(),
            **exec_payload,
        )
        client_class = AzureRealtimeWebsocket
    elif service == "azure_voice_live":
        execution_settings = AzureVoiceLiveExecutionSettings(
            function_choice_behavior=FunctionChoiceBehavior.Auto(),
            **exec_payload,
        )
        client_class = AzureVoiceLiveWebsocket
    else:
        raise ValueError(f"Unknown service: {service}")

    chat_history.add_system_message(execution_settings.instructions)

    return client_class(
        endpoint=settings.AZURE_AI_SERVICES_ENDPOINT,
        deployment_name=deployment_name,
        ad_token_provider=get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        ),
        api_version=api_version,
        plugins=plugins,
        settings=execution_settings,
    )

async def handle_realtime_messages(websocket: WebSocket, client: RealtimeClientBase, chat_history: ChatHistory):
    """Function that handles the messages from the Realtime service.

    This function only handles the non-audio messages.
    Audio is done through the callback so that it is faster and smoother.
    """

    async def from_realtime_to_acs(audio: ndarray):
        """Function that forwards the audio from the model to the websocket of the ACS client."""
        logger.debug("Audio received from the model, sending to ACS client")
        await websocket.send_text(
            json.dumps(
                {
                    "kind": "AudioData",
                    "audioData": {
                        "data": base64.b64encode(audio.tobytes()).decode("utf-8")
                    },
                }
            )
        )

    idx_first_msg_to_send = len(chat_history.messages)  # Chat history will contain system prompt
    async for event in client.receive(audio_output_callback=from_realtime_to_acs):
        match event.service_type:
            case ListenEvents.SESSION_CREATED:
                logger.info("Session Created Message")
                logger.debug(f"  Session Id: {event.service_event.session.id}")
            case ListenEvents.ERROR:
                logger.error(f"  Error: {event.service_event.error}")
            case ListenEvents.INPUT_AUDIO_BUFFER_CLEARED:
                logger.info("Input Audio Buffer Cleared Message")
            case ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                logger.debug(
                    f"Voice activity detection started at {event.service_event.audio_start_ms} [ms]"
                )
                await websocket.send_text(
                    json.dumps(
                        {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
                    )
                )
            case ListenEvents.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logger.info(f" User:-- {event.service_event.transcript}")
            case ListenEvents.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_FAILED:
                logger.error(f"  Error: {event.service_event.error}")
            case ListenEvents.RESPONSE_DONE:
                logger.info("Response Done Message")
                logger.debug(f"  Response Id: {event.service_event.response.id}")
                if event.service_event.response.status_details:
                    logger.debug(
                        f"  Status Details: {event.service_event.response.status_details.model_dump_json()}"
                    )
                # Send chat history (including function calls) to client
                await websocket.send_text(
                    json.dumps(
                        {
                            "kind": "ChatHistory",
                            "data": export_chat_history(chat_history, from_index=idx_first_msg_to_send)
                        }
                    )
                )
                idx_first_msg_to_send = len(chat_history.messages)
            case ListenEvents.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                logger.info(f" AI:-- {event.service_event.transcript}")
                # Add assistant message to chat history
                chat_history.add_assistant_message(event.service_event.transcript)
            # case ListenEvents.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
                # Add function call to chat history
                # Disabling for now - redundant with function result?
                # chat_history.add_tool_message([event.function_call])
            case SendEvents.CONVERSATION_ITEM_CREATE:
                # Add function call result to chat history
                chat_history.add_tool_message([event.function_result])
