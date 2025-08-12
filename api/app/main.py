import asyncio
import base64
import json
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from numpy import ndarray
from semantic_kernel.connectors.ai.open_ai import ListenEvents, SendEvents
from semantic_kernel.connectors.ai.realtime_client_base import \
    RealtimeClientBase
from semantic_kernel.contents import (AudioContent, ChatHistory,
                                      RealtimeAudioEvent)

from .config import settings
from .dependencies import get_acs_client
from .plugins import CallPlugin, DeliveryPlugin
from .routers import calls
from .sk_utils import export_chat_history, get_agent

app = FastAPI()

# Mount static files and add routers
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")
app.include_router(calls.router)

# Configure root logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger().setLevel(LOG_LEVEL)
logger = logging.getLogger(__name__)


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
                logger.debug(f"  Session Id: {event.service_event.session.id}")  # type: ignore
            case ListenEvents.ERROR:
                logger.error(f"  Error: {event.service_event.error}")  # type: ignore
            case ListenEvents.INPUT_AUDIO_BUFFER_CLEARED:
                logger.info("Input Audio Buffer Cleared Message")
            case ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                logger.debug(
                    f"Voice activity detection started at {event.service_event.audio_start_ms} [ms]"  # type: ignore
                )
                await websocket.send_text(
                    json.dumps(
                        {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
                    )
                )
            case ListenEvents.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logger.info(f" User:-- {event.service_event.transcript}")  # type: ignore
            case ListenEvents.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_FAILED:
                logger.error(f"  Error: {event.service_event.error}")  # type: ignore
            case ListenEvents.RESPONSE_DONE:
                logger.info("Response Done Message")
                logger.debug(f"  Response Id: {event.service_event.response.id}")  # type: ignore
                if event.service_event.response.status_details:  # type: ignore
                    logger.debug(
                        f"  Status Details: {event.service_event.response.status_details.model_dump_json()}"  # type: ignore
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
                logger.info(f" AI:-- {event.service_event.transcript}")  # type: ignore
                # Add assistant message to chat history
                chat_history.add_assistant_message(event.service_event.transcript)
            # case ListenEvents.RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
                # Add function call to chat history
                # Disabling for now - redundant with function result?
                # chat_history.add_tool_message([event.function_call])
            case SendEvents.CONVERSATION_ITEM_CREATE:
                # Add function call result to chat history
                chat_history.add_tool_message([event.function_result])


@app.get("/")
async def root():
    """Serve the main frontend page."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.websocket("/ws")
async def agent_connect(websocket: WebSocket, acs_client=Depends(get_acs_client)):
    """Websocket endpoint for connecting from ACS Audio Stream to the agent."""
    await websocket.accept()
    call_connection_id = websocket.headers.get("x-ms-call-connection-id")

    if not call_connection_id:
        logger.warning("No call connection ID provided in headers indicating direct connection (not ACS). Certain call functions won't work.")

    # Load realtime agent from template and plugins
    chat_history = ChatHistory()
    realtime_agent = await get_agent(
        template_name="DeliveryAgent",
        plugins=[
            CallPlugin(acs_client=acs_client, call_connection_id=call_connection_id),
            DeliveryPlugin()
        ],
        chat_history=chat_history,
        agent_name="Archie"
    )

    # Create the realtime client session
    async with realtime_agent(create_response=True) as client:
        # Start handling the messages from the realtime client with callback to forward the audio to acs
        receive_task = asyncio.create_task(
            handle_realtime_messages(websocket, realtime_agent, chat_history)
        )
        # Receive messages from the ACS client and send them to the realtime client
        while True:
            try:
                # Receive data from the ACS client
                stream_data = await websocket.receive_text()
                data = json.loads(stream_data)
                logger.debug(f"Received data from ACS client: {data}")

                # If audio send it to the Realtime service
                if data["kind"] == "AudioData":
                    await client.send(
                        event=RealtimeAudioEvent(
                            audio=AudioContent(
                                data=data["audioData"]["data"],
                                data_format="base64",
                                inner_content=data,
                            ),
                        )
                    )
            except Exception:
                logger.info("Websocket connection closed.")
                break

        receive_task.cancel()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
