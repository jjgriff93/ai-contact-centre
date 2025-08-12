import logging
import os
import uuid
from urllib.parse import urlencode, urlparse, urlunparse

from azure.communication.callautomation import (AudioFormat,
                                                MediaStreamingAudioChannelType,
                                                MediaStreamingContentType,
                                                MediaStreamingOptions,
                                                StreamingTransportType)
from azure.eventgrid import EventGridEvent, SystemEventNames
from fastapi import APIRouter, Depends

from ..config import settings
from ..dependencies import get_acs_client

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/calls/incoming")
async def incoming_call_handler(events: list[dict], acs_client=Depends(get_acs_client)):
    """Handle incoming call events from Azure Communication Services."""
    # This should be set in env when running locally to devtunnel uri
    if not settings.AZURE_ACS_CALLBACK_HOST_URI:
        # When running in container app, this will be the request host uri
        logger.debug("AZURE_ACS_CALLBACK_HOST_URI is not set. Using container hostname.")
        container_app_hostname = os.environ.get("CONTAINER_APP_HOSTNAME")

        if not container_app_hostname:
            logger.error("CONTAINER_APP_HOSTNAME is not set. Cannot determine callback base URI.")
            raise ValueError("AZURE_ACS_CALLBACK_HOST_URI or CONTAINER_APP_HOSTNAME environment variable is required.")

        callback_base_uri = "https://" + container_app_hostname
    else:
        callback_base_uri = settings.AZURE_ACS_CALLBACK_HOST_URI

    # Set the callback events URI to our API route for responding to call events
    callback_events_uri = f"{callback_base_uri}/api/callbacks"
    logger.info(f"Call event received. Using callback events URI: {callback_events_uri}")
  
    for event_dict in events:
        event = EventGridEvent.from_dict(event_dict)

        match event.event_type:
            case SystemEventNames.EventGridSubscriptionValidationEventName:
                logger.info("Validating subscription")
                validation_code = event.data["validationCode"]
                validation_response = {"validationResponse": validation_code}
                return validation_response

            case SystemEventNames.AcsIncomingCallEventName:
                logger.debug("Incoming call received: data=%s", event.data)
                caller_id = (
                    event.data["from"]["phoneNumber"]["value"]
                    if event.data["from"]["kind"] == "phoneNumber"
                    else event.data["from"]["rawId"]
                )

                logger.info("incoming call handler caller id: %s", caller_id)
                incoming_call_context = event.data["incomingCallContext"]
                guid = uuid.uuid4()
                query_parameters = urlencode({"callerId": caller_id})
                callback_uri = f"{callback_events_uri}/{guid}?{query_parameters}"

                parsed_url = urlparse(callback_events_uri)
                websocket_url = urlunparse(("wss", parsed_url.netloc, "/ws", "", "", ""))

                logger.debug("callback url: %s", callback_uri)
                logger.debug("websocket url: %s", websocket_url)

                # Answer the call and direct ACS media streaming to the websocket endpoint
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
                logger.info(f"Answered call for connection id: {answer_call_result.call_connection_id}")
            case _:
                logger.debug("Event type not handled: %s", event.event_type)
                logger.debug("Event data: %s", event.data)

@router.post("/calls/callbacks/{contextId}")
async def callbacks(contextId: str, events: list[dict], acs_client=Depends(get_acs_client)):
    """Handle callback events from Azure Communication Services during a call."""
    for event in events:
        # Parsing callback events
        event_data = event["data"]
        call_connection_id = event_data["callConnectionId"]
        logger.debug(
            f"Received Event:-> {event['type']}, Correlation Id:-> {event_data['correlationId']}, ContextId:-> {contextId}, CallConnectionId:-> {call_connection_id}"
        )

        match event["type"]:
            case "Microsoft.Communication.CallConnected":
                call_connection_properties = await acs_client.get_call_connection(
                    call_connection_id
                ).get_call_properties()
                media_streaming_subscription = call_connection_properties.media_streaming_subscription
                logger.info(f"MediaStreamingSubscription:--> {media_streaming_subscription}")
                logger.info(f"Received CallConnected event for connection id: {call_connection_id}")
                logger.debug("CORRELATION ID:--> %s", event_data["correlationId"])
                logger.debug("CALL CONNECTION ID:--> %s", event_data["callConnectionId"])

            case "Microsoft.Communication.MediaStreamingStarted" | "Microsoft.Communication.MediaStreamingStopped":
                logger.debug(
                    f"Media streaming content type:--> {event_data['mediaStreamingUpdate']['contentType']}"
                )
                logger.debug(
                    f"Media streaming status:--> {event_data['mediaStreamingUpdate']['mediaStreamingStatus']}"
                )
                logger.debug(
                    f"Media streaming status details:--> {event_data['mediaStreamingUpdate']['mediaStreamingStatusDetails']}"  # noqa: E501
                )

            case "Microsoft.Communication.MediaStreamingFailed":
                logger.warning(
                    f"Code:->{event_data['resultInformation']['code']}, Subcode:-> {event_data['resultInformation']['subCode']}"  # noqa: E501
                )
                logger.warning(f"Message:->{event_data['resultInformation']['message']}")

            case "Microsoft.Communication.CallDisconnected":
                logger.debug(f"Call disconnected for connection id: {call_connection_id}")
