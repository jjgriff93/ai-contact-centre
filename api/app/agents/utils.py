import base64
import json
import logging
from pathlib import Path

import yaml
from azure.identity.aio import (DefaultAzureCredential,
                                get_bearer_token_provider)
from fastapi import WebSocket
from numpy import ndarray
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import ListenEvents, SendEvents
from semantic_kernel.connectors.ai.realtime_client_base import \
    RealtimeClientBase
from semantic_kernel.contents import (ChatHistory, FunctionCallContent,
                                      FunctionResultContent)
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import (KernelPromptTemplate,
                                             PromptTemplateConfig)

from ..config import settings
from .azure_voice_live import (AzureVoiceLiveExecutionSettings,
                               AzureVoiceLiveInputAudioEchoCancellation,
                               AzureVoiceLiveInputAudioNoiseReduction,
                               AzureVoiceLiveTurnDetection,
                               AzureVoiceLiveVoiceConfig,
                               AzureVoiceLiveWebsocket)

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

    rendered_prompt = await prompt_template.render(Kernel(), prompt_arguments)
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
        # TODO: adding transcription currently causes stream to disconnect. Investigate
        # input_audio_transcription=AzureVoiceLiveInputAudioTranscription(
        #     model="azure-fast-transcription"
        # ),
        function_choice_behavior=FunctionChoiceBehavior.Auto(),
    )

    chat_history.add_system_message(execution_settings.instructions)

    return AzureVoiceLiveWebsocket(
        endpoint=settings.AZURE_AI_SERVICES_ENDPOINT,
        deployment_name="gpt-4o-realtime-preview",
        ad_token_provider=get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        ),
        api_version="2025-05-01-preview",
        plugins=plugins,
        settings=execution_settings
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
