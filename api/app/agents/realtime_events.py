import base64
import json
import logging

from fastapi import WebSocket
from numpy import ndarray
from semantic_kernel.connectors.ai.open_ai import ListenEvents, SendEvents
from semantic_kernel.connectors.ai.realtime_client_base import \
    RealtimeClientBase
from semantic_kernel.contents import ChatHistory

from .utils import get_attr, send_chat_history

logger = logging.getLogger(__name__)


async def handle_realtime_messages(
    websocket: WebSocket,
    client: RealtimeClientBase,
    chat_history: ChatHistory,
    is_development_mode: bool = False,
):
    """Handle non-audio realtime service messages and forward audio via callback.

    Audio data is streamed through the callback for lower latency; this loop only
    processes control, transcript, and tool/function events.
    """

    async def from_realtime_to_acs(audio: ndarray):
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

    idx_first_msg_to_send = len(chat_history.messages)  # Includes system prompt

    try:
        async for event in client.receive(audio_output_callback=from_realtime_to_acs):
            se = getattr(event, "service_event", None)
            match event.service_type:
                case ListenEvents.SESSION_CREATED:
                    logger.info("Session Created Message")
                    logger.debug(
                        f"  Session Id: {get_attr(se, 'session.id') or '<unknown>'}"
                    )
                case ListenEvents.ERROR:
                    err = get_attr(se, "error") or "<unknown>"
                    logger.error(f"  Error: {err}")
                    chat_history.add_assistant_message(
                        "I hit a temporary issue calling a tool. Let's try again or continue without it."
                    )
                    idx_first_msg_to_send = await send_chat_history(
                        websocket, chat_history, idx_first_msg_to_send
                    )
                case ListenEvents.INPUT_AUDIO_BUFFER_CLEARED:
                    logger.info("Input Audio Buffer Cleared Message")
                case ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                    audio_start_ms = get_attr(se, "audio_start_ms")
                    logger.debug(
                        "Voice activity detection started at %s [ms]",
                        audio_start_ms if audio_start_ms is not None else "<unknown>",
                    )
                    await websocket.send_text(
                        json.dumps(
                            {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
                        )
                    )
                case ListenEvents.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                    user_transcript = get_attr(se, "transcript") or ""
                    logger.info(f" User:-- {user_transcript}")
                    if user_transcript:
                        chat_history.add_user_message(user_transcript)
                    if is_development_mode:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "kind": "Transcription",
                                    "data": {
                                        "speaker": "user",
                                        "text": user_transcript,
                                        "timestamp": get_attr(se, "audio_start_ms") or 0,
                                    },
                                }
                            )
                        )
                case ListenEvents.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_FAILED:
                    logger.error(
                        f"  Error: {get_attr(se, 'error') or '<unknown>'}"
                    )
                case ListenEvents.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                    transcript = get_attr(se, "transcript")
                    logger.info(f" AI:-- {transcript or ''}")
                    if transcript:
                        chat_history.add_assistant_message(transcript)
                        if is_development_mode:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "kind": "Transcription",
                                        "data": {
                                            "speaker": "assistant",
                                            "text": transcript,
                                            "timestamp": None,
                                        },
                                    }
                                )
                            )
                case ListenEvents.RESPONSE_DONE:
                    logger.info("Response Done Message")
                    response = get_attr(se, "response")
                    response_id = get_attr(response, "id")
                    logger.debug(f"  Response Id: {response_id or '<unknown>'}")
                    status_details = get_attr(response, "status_details")
                    if status_details:
                        try:
                            logger.debug(
                                f"  Status Details: {status_details.model_dump_json()}"
                            )
                        except Exception:
                            logger.debug(
                                "  Status Details present but could not be serialized"
                            )
                    idx_first_msg_to_send = await send_chat_history(
                        websocket, chat_history, idx_first_msg_to_send
                    )
                case SendEvents.CONVERSATION_ITEM_CREATE:
                    function_result = getattr(event, "function_result", None)
                    if function_result is not None:
                        chat_history.add_tool_message([function_result])
    except Exception as e:
        logger.exception("Realtime receive loop terminated due to error")
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "kind": "AgentError",
                        "message": "A tool call failed. The assistant will continue.",
                        "details": str(e),
                    }
                )
            )
        except Exception:
            pass
