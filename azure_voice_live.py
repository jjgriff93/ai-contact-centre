import logging
import sys
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Union,
)

from openai.types.beta.realtime.session import Tool, Tracing
from openai.types.beta.realtime.session_update_event_param import SessionClientSecret
from pydantic import Field
from semantic_kernel.connectors.ai import PromptExecutionSettings
from semantic_kernel.connectors.ai.open_ai import AzureRealtimeWebsocket, SendEvents
from semantic_kernel.contents import RealtimeEvents
from semantic_kernel.kernel_pydantic import KernelBaseModel

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


logger: logging.Logger = logging.getLogger(
    "semantic_kernel.connectors.ai.open_ai.realtime"
)


class AzureVoiceLiveEndOfUtteranceDetection(KernelBaseModel):
    """End of utterance detection settings.

    Args:
        model: The model to use for end of utterance detection, should be one of the following:
            - semantic_detection_v1
        type: The type of end of utterance detection, should be azure_semantic_vad.
    """

    model: Literal["semantic_detection_v1"] | None = None
    threshold: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    timeout: Annotated[int | None, Field(ge=0)] = None


class AzureVoiceLiveInputAudioNoiseReduction(KernelBaseModel):
    type: Optional[Literal["azure_deep_noise_suppression"]] = None


class AzureVoiceLiveInputAudioEchoCancellation(KernelBaseModel):
    type: Optional[Literal["server_echo_cancellation"]] = None


class AzureVoiceLiveInputAudioTranscription(KernelBaseModel):
    """Input audio transcription settings.

    Args:
        model: The model to use for transcription, should be one of the following:
            - azure-fast-transcription
        phrase_list: A list of phrases to help the model recognize specific terms or phrases in the audio.
            Currently doesn't support gpt-4o-realtime-preview, gpt-4o-mini-realtime-preview, and phi4-mm-realtime.
    """

    model: Literal["azure-fast-transcription"] | None = None
    phrase_list: Sequence[str] | None = None


class AzureVoiceLiveAnimation(KernelBaseModel):
    """Animation output settings."""

    outputs: Sequence[Literal["viseme_id"]] | None = None
    """Enable animation output by specifying outputs, currently only supports viseme_id."""


class AzureVoiceLiveTurnDetection(KernelBaseModel):
    """Turn detection settings.

    Args:
        type: The type of turn detection, server_vad or azure_semantic_vad.
        create_response: Whether to create a response for each detected turn.
        eagerness: The eagerness of the voice activity detection, can be low, medium, high, or auto,
            used only for semantic_vad.
        interrupt_response: Whether to interrupt the response for each detected turn.
        prefix_padding_ms: The padding before the detected voice activity, in milliseconds.
        silence_duration_ms: The duration of silence to detect the end of a turn, in milliseconds.
        threshold: The threshold for voice activity detection, should be between 0 and 1, only for server_vad.
        remove_filler_words: Whether to remove filler words from the detected turns, only for azure_semantic_vad.
        end_of_utterance_detection: Optional end of utterance detection settings, only for azure_semantic_vad.
    """

    type: Literal["server_vad", "azure_semantic_vad"] = "server_vad"
    create_response: bool | None = None
    eagerness: Literal["low", "medium", "high", "auto"] | None = None
    interrupt_response: bool | None = None
    prefix_padding_ms: Annotated[int | None, Field(ge=0)] = None
    silence_duration_ms: Annotated[int | None, Field(ge=0)] = None
    threshold: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    remove_filler_words: bool | None = None
    end_of_utterance_detection: AzureVoiceLiveEndOfUtteranceDetection | None = None


class AzureVoiceLiveVoiceConfig(KernelBaseModel):
    """Voice settings for Azure Voice Live API.

    Args:
        name: The name of the voice.
        type: The type of voice, either azure-standard or azure-custom.
        temperature: The temperature for the voice, should be between 0.0 and 1.0.
        rate: The speaking rate of the voice, e.g., "1.0" for normal speed.
        endpoint_id: The endpoint ID for the custom voice, if applicable.
        custom_lexicon_url: The URL for a custom lexicon, if applicable.
    """

    name: str | None = None
    type: Literal["azure-standard", "azure-custom"] | None = None
    temperature: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    rate: str | None = None
    endpoint_id: str | None = None
    custom_lexicon_url: str | None = None


class AzureVoiceLiveExecutionSettings(PromptExecutionSettings):
    """Request settings for Azure Voice Live API."""

    modalities: Sequence[Literal["audio", "text"]] | None = None
    ai_model_id: Annotated[str | None, Field(None, serialization_alias="model")] = None
    instructions: str | None = None
    voice: AzureVoiceLiveVoiceConfig | Dict[str, Any] | None = None
    input_audio_sampling_rate: Literal[16000, 24000] | None = None
    input_audio_noise_reduction: AzureVoiceLiveInputAudioNoiseReduction | None = None
    input_audio_echo_cancellation: AzureVoiceLiveInputAudioEchoCancellation | None = (
        None
    )
    input_audio_format: Literal["pcm16", "g711_ulaw", "g711_alaw"] | None = None
    output_audio_format: Literal["pcm16", "g711_ulaw", "g711_alaw"] | None = None
    input_audio_transcription: (
        AzureVoiceLiveInputAudioTranscription | Mapping[str, Any] | None
    ) = None
    turn_detection: AzureVoiceLiveTurnDetection | Mapping[str, str] | None = None
    tools: Annotated[
        list[dict[str, Any]] | None,
        Field(
            description="Do not set this manually. It is set by the service based "
            "on the function choice configuration.",
        ),
    ] = None
    tool_choice: Annotated[
        str | None,
        Field(
            description="Do not set this manually. It is set by the service based "
            "on the function choice configuration.",
        ),
    ] = None
    temperature: Annotated[float | None, Field(ge=0.6, le=1.2)] = None
    max_response_output_tokens: Annotated[int | Literal["inf"] | None, Field(gt=0)] = (
        None
    )
    animation: AzureVoiceLiveAnimation | None = None


class AzureVoiceLiveSession(KernelBaseModel):
    """Session configuration for Azure Voice Live API.

    Similar to OpenAI Realtime session with some differences."""

    client_secret: Optional[SessionClientSecret] = None
    input_audio_format: Optional[Literal["pcm16", "g711_ulaw", "g711_alaw"]] = None
    input_audio_noise_reduction: Optional[AzureVoiceLiveInputAudioNoiseReduction] = None
    input_audio_transcription: Optional[AzureVoiceLiveInputAudioTranscription] = None
    input_audio_sampling_rate: Literal[16000, 24000] | None = None
    instructions: Optional[str] = None
    max_response_output_tokens: Union[int, Literal["inf"], None] = None
    modalities: Optional[List[Literal["text", "audio"]]] = None
    model: Optional[str] = None
    output_audio_format: Optional[Literal["pcm16", "g711_ulaw", "g711_alaw"]] = None
    speed: Optional[float] = None
    temperature: Optional[float] = None
    tool_choice: Optional[str] = None
    tools: Optional[List[Tool]] = None
    tracing: Optional[Tracing] = None
    turn_detection: Optional[AzureVoiceLiveTurnDetection] = None
    voice: Optional[AzureVoiceLiveVoiceConfig] = None
    animation: Optional[AzureVoiceLiveAnimation] = None


class AzureVoiceLiveWebsocket(AzureRealtimeWebsocket):
    """Azure Voice Live Websocket client."""

    def __init__(
        self,
        endpoint: str,
        **kwargs: Any,
    ):
        # Voice Live uses a slightly different path structure to OpenAI Realtime
        voicelive_ws_endpoint = endpoint.replace("https://", "wss://") + "voice-live"
        super().__init__(
            endpoint=endpoint,
            websocket_base_url=voicelive_ws_endpoint,
            **kwargs,
        )

    @override
    def get_prompt_execution_settings_class(self) -> type[PromptExecutionSettings]:
        return AzureVoiceLiveExecutionSettings

    @override
    async def send(self, event: RealtimeEvents, **kwargs: Any) -> None:
        """Send an event to the Websocket client. We need to override to handle the modified session update event"""
        if event.service_type == SendEvents.SESSION_UPDATE:
            data = event.service_event
            if not data:
                logger.error("Event data is empty")
                return
            settings = data.get("settings", None)
            if not settings:
                logger.error("Event data does not contain 'settings'")
                return
            try:
                settings = self.get_prompt_execution_settings_from_settings(settings)
            except Exception as e:
                logger.error(
                    f"Failed to properly create settings from passed settings: {settings}, error: {e}"
                )
                return
            assert isinstance(settings, self.get_prompt_execution_settings_class())  # nosec
            if not settings.ai_model_id:  # type: ignore
                settings.ai_model_id = self.ai_model_id  # type: ignore
            # Pass the event as a dictionary instead of Pydantic model to avoid OpenAI SDK validation error in send()
            await self._send(
                {
                    "type": SendEvents.SESSION_UPDATE.value,
                    "session": settings.prepare_settings_dict(),  # type: ignore
                }
            )
        else:
            await super().send(event, **kwargs)
