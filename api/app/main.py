import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse

from azure.communication.callautomation import (AudioFormat,
                                                MediaStreamingAudioChannelType,
                                                MediaStreamingContentType,
                                                MediaStreamingOptions,
                                                StreamingTransportType)
from azure.communication.callautomation.aio import CallAutomationClient
from azure.eventgrid import EventGridEvent, SystemEventNames
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from fastapi import FastAPI, Request, WebSocket
from numpy import ndarray
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import ListenEvents
from semantic_kernel.connectors.ai.realtime_client_base import \
    RealtimeClientBase
from semantic_kernel.contents import AudioContent, RealtimeAudioEvent

from .azure_voice_live import (AzureVoiceLiveExecutionSettings,
                               AzureVoiceLiveInputAudioEchoCancellation,
                               AzureVoiceLiveInputAudioNoiseReduction,
                               AzureVoiceLiveTurnDetection,
                               AzureVoiceLiveVoiceConfig,
                               AzureVoiceLiveWebsocket)
from .plugins.call import CallPlugin

# TODO: this won't come from a .env in production, will it?
DOTENV = os.path.join(os.path.dirname(__file__), ".env")

class Settings(BaseSettings):
    ACS_ENDPOINT: str = Field(..., description='Azure Communication Services endpoint')
    AZURE_FOUNDRY_ENDPOINT: str = Field(..., description='Azure Cognitive Services endpoint')
    ACS_CALLBACK_HOST_URI: Optional[str] = Field(..., description='Callback host URI for webhooks. If not specified will use the requests host URI.')

    model_config = SettingsConfigDict(env_file=DOTENV, env_file_encoding='utf-8')

settings = Settings() # type: ignore
app = FastAPI()

credential = DefaultAzureCredential()

acs_client = CallAutomationClient(settings.ACS_ENDPOINT, credential) # type: ignore


async def handle_realtime_messages(websocket: WebSocket, client: RealtimeClientBase):
    """Function that handles the messages from the Realtime service.

    This function only handles the non-audio messages.
    Audio is done through the callback so that it is faster and smoother.
    """

    async def from_realtime_to_acs(audio: ndarray):
        """Function that forwards the audio from the model to the websocket of the ACS client."""
        logging.debug("Audio received from the model, sending to ACS client")
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

    async for event in client.receive(audio_output_callback=from_realtime_to_acs):
        match event.service_type:
            case ListenEvents.SESSION_CREATED:
                logging.info("Session Created Message")
                logging.debug(f"  Session Id: {event.service_event.session.id}")  # type: ignore
            case ListenEvents.ERROR:
                logging.error(f"  Error: {event.service_event.error}")  # type: ignore
            case ListenEvents.INPUT_AUDIO_BUFFER_CLEARED:
                logging.info("Input Audio Buffer Cleared Message")
            case ListenEvents.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                logging.debug(
                    f"Voice activity detection started at {event.service_event.audio_start_ms} [ms]"  # type: ignore
                )
                await websocket.send_text(
                    json.dumps(
                        {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
                    )
                )
            case ListenEvents.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                logging.info(f" User:-- {event.service_event.transcript}")  # type: ignore
            case ListenEvents.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_FAILED:
                logging.error(f"  Error: {event.service_event.error}")  # type: ignore
            case ListenEvents.RESPONSE_DONE:
                logging.info("Response Done Message")
                logging.debug(f"  Response Id: {event.service_event.response.id}")  # type: ignore
                if event.service_event.response.status_details:  # type: ignore
                    logging.debug(
                        f"  Status Details: {event.service_event.response.status_details.model_dump_json()}"  # type: ignore
                    )
            case ListenEvents.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                logging.info(f" AI:-- {event.service_event.transcript}")  # type: ignore


@app.websocket("/ws")
async def agent_connect(websocket: WebSocket):
    await websocket.accept()
    call_connection_id = websocket.headers.get("x-ms-call-connection-id")

    if not call_connection_id:
        logging.error("No call connection ID provided in headers.")
        await websocket.close(code=1008, reason="No call connection ID provided.")
        return

    kernel = Kernel()
    kernel.add_plugin(
        plugin=CallPlugin(acs_client=acs_client, call_connection_id=call_connection_id),
        plugin_name="call",
        description="Functions for managing the ACS call",
    )

    realtime_client = AzureVoiceLiveWebsocket(
        endpoint=settings.AZURE_FOUNDRY_ENDPOINT,
        deployment_name="gpt-4o-realtime-preview",
        ad_token_provider=get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default",
        ),
        api_version="2025-05-01-preview",
    )
    print(f"Connecting to Realtime API at {realtime_client.client.websocket_base_url}")

    # Create the settings for the session
    execution_settings = AzureVoiceLiveExecutionSettings(
        instructions="""
    You are a chat bot. Your name is Mosscap and
    you have one goal: figure out what people need.
    Your full name, should you need to know it, is
    Splendid Speckled Mosscap. You communicate
    effectively, but you tend to answer with long
    flowery prose.
    """,
        voice=AzureVoiceLiveVoiceConfig(
            name="en-US-Ava:DragonHDLatestNeural",
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
    )

    async def from_acs_to_realtime(client: RealtimeClientBase):
        """Function that forwards the audio from the ACS client to the model."""
        while True:
            try:
                # Receive data from the ACS client
                stream_data = await websocket.receive_text()
                data = json.loads(stream_data)
                if data["kind"] == "AudioData":
                    # send it to the Realtime service
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
                logging.info("Websocket connection closed.")
                break

    # Create the realtime client session
    async with realtime_client(settings=execution_settings, create_response=True, kernel=kernel):
        # start handling the messages from the realtime client with callback to forward the audio to acs
        receive_task = asyncio.create_task(
            handle_realtime_messages(websocket, realtime_client)
        )
        # receive messages from the ACS client and send them to the realtime client
        await from_acs_to_realtime(realtime_client)
        receive_task.cancel()


@app.post("/api/incomingCall")
async def incoming_call_handler(events: list[dict], request: Request):
    """Handle incoming call events from Azure Communication Services."""
    # This should be set in env when running locally to devtunnel uri
    if not settings.ACS_CALLBACK_HOST_URI:
        logging.debug("ACS_CALLBACK_HOST_URI is not set. Using host URI.")
        callback_events_uri = str(request.base_url) + "/api/callbacks"
    # When running in container app, this will be the request host uri
    else:
        callback_events_uri = settings.ACS_CALLBACK_HOST_URI + "/api/callbacks"
    for event_dict in events:
        event = EventGridEvent.from_dict(event_dict)
        match event.event_type:
            case SystemEventNames.EventGridSubscriptionValidationEventName:
                logging.info("Validating subscription")
                validation_code = event.data["validationCode"]
                validation_response = {"validationResponse": validation_code}
                return validation_response
            case SystemEventNames.AcsIncomingCallEventName:
                logging.debug("Incoming call received: data=%s", event.data)
                caller_id = (
                    event.data["from"]["phoneNumber"]["value"]
                    if event.data["from"]["kind"] == "phoneNumber"
                    else event.data["from"]["rawId"]
                )
                logging.info("incoming call handler caller id: %s", caller_id)
                incoming_call_context = event.data["incomingCallContext"]
                guid = uuid.uuid4()
                query_parameters = urlencode({"callerId": caller_id})
                callback_uri = f"{callback_events_uri}/{guid}?{query_parameters}"

                parsed_url = urlparse(callback_events_uri)
                websocket_url = urlunparse(("wss", parsed_url.netloc, "/ws", "", "", ""))

                logging.debug("callback url: %s", callback_uri)
                logging.debug("websocket url: %s", websocket_url)

                answer_call_result = await acs_client.answer_call(
                    incoming_call_context=incoming_call_context,
                    operation_context="incomingCall",
                    callback_url=callback_uri,
                    media_streaming=MediaStreamingOptions(
                        transport_url=websocket_url,
                        transport_type=StreamingTransportType.WEBSOCKET,
                        content_type=MediaStreamingContentType.AUDIO,
                        audio_channel_type=MediaStreamingAudioChannelType.MIXED,
                        start_media_streaming=True,
                        enable_bidirectional=True,
                        audio_format=AudioFormat.PCM24_K_MONO,
                    ),
                )
                logging.info(f"Answered call for connection id: {answer_call_result.call_connection_id}")
            case _:
                logging.debug("Event type not handled: %s", event.event_type)
                logging.debug("Event data: %s", event.data)


@app.post("/api/callbacks/{contextId}")
async def callbacks(contextId: str, events: list[dict]):
    for event in events:
        # Parsing callback events
        event_data = event["data"]
        call_connection_id = event_data["callConnectionId"]
        logging.debug(
            f"Received Event:-> {event['type']}, Correlation Id:-> {event_data['correlationId']}, ContextId:-> {contextId}, CallConnectionId:-> {call_connection_id}"
        )
        match event["type"]:
            case "Microsoft.Communication.CallConnected":
                call_connection_properties = await acs_client.get_call_connection(
                    call_connection_id
                ).get_call_properties()
                media_streaming_subscription = call_connection_properties.media_streaming_subscription
                logging.info(f"MediaStreamingSubscription:--> {media_streaming_subscription}")
                logging.info(f"Received CallConnected event for connection id: {call_connection_id}")
                logging.debug("CORRELATION ID:--> %s", event_data["correlationId"])
                logging.debug("CALL CONNECTION ID:--> %s", event_data["callConnectionId"])
            case "Microsoft.Communication.MediaStreamingStarted" | "Microsoft.Communication.MediaStreamingStopped":
                logging.debug(
                    f"Media streaming content type:--> {event_data['mediaStreamingUpdate']['contentType']}"
                )
                logging.debug(
                    f"Media streaming status:--> {event_data['mediaStreamingUpdate']['mediaStreamingStatus']}"
                )
                logging.debug(
                    f"Media streaming status details:--> {event_data['mediaStreamingUpdate']['mediaStreamingStatusDetails']}"  # noqa: E501
                )
            case "Microsoft.Communication.MediaStreamingFailed":
                logging.warning(
                    f"Code:->{event_data['resultInformation']['code']}, Subcode:-> {event_data['resultInformation']['subCode']}"  # noqa: E501
                )
                logging.warning(f"Message:->{event_data['resultInformation']['message']}")
            case "Microsoft.Communication.CallDisconnected":
                logging.debug(f"Call disconnected for connection id: {call_connection_id}")
            case "Microsoft.Communication.CallDisconnected":
                logging.debug(f"Call disconnected for connection id: {call_connection_id}")
                logging.debug(f"Call disconnected for connection id: {call_connection_id}")
