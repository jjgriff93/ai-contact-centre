import base64
import json
import logging
import time
import wave
from typing import List, Optional, Tuple, Literal, Dict
import asyncio
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Audio format constants (match TTS/STT expectations)
SAMPLE_RATE_HZ = 24_000
SAMPLE_WIDTH_BYTES = 2  # 16-bit PCM
CHANNELS = 1

SegmentRole = Literal["assistant", "customer"]
ConversationSegment = Tuple[SegmentRole, bytes, float]


class VoiceCallClient:
    """Test harness for simulating ACS calls to the voice AI system over WebSocket."""

    def __init__(self, websocket_url: str = "ws://localhost:8000/ws") -> None:
        self.websocket_url = websocket_url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None

        # Buffers
        self.audio_buffer = bytearray()
        self.customer_audio_buffer = bytearray()  # Customer audio only
        self.current_assistant_audio = bytearray()  # Buffer for current assistant turn

        # Timeline of segments: (role, audio_data, timestamp)
        self.conversation_segments: List[ConversationSegment] = []

        # Activity tracking
        self.last_audio_received_time: Optional[float] = None
        self.last_assistant_activity_time: Optional[float] = None
        self.is_assistant_speaking: bool = False

        # NEW: timing for the in-progress assistant turn
        self.current_assistant_turn_started_at: Optional[float] = None

        # Conversation history
        self.chat_history: List[Dict] = []

    async def connect(self, call_connection_id: str = "test-connection-123") -> None:
        """Connect to the WebSocket endpoint with the required headers."""
        headers = {"x-ms-call-connection-id": call_connection_id}
        logger.info("Connecting to %s ...", self.websocket_url)
        self.websocket = await websockets.connect(
            self.websocket_url,
            additional_headers=headers,  # websockets uses 'additional_headers'
        )
        logger.info("Connected to %s", self.websocket_url)

    async def send_audio_chunk(self, audio_data: bytes) -> None:
        """Send an audio chunk to the WebSocket (base64-encoded PCM)."""
        if not self.websocket:
            raise RuntimeError("Not connected")

        message = {
            "kind": "AudioData",
            "audioData": {"data": base64.b64encode(audio_data).decode("utf-8")},
        }
        await self.websocket.send(json.dumps(message))

    def add_customer_audio(self, audio_data: bytes) -> None:
        """Record a customer audio segment into the conversation timeline."""
        self.customer_audio_buffer.extend(audio_data)
        self.conversation_segments.append(("customer", bytes(audio_data), time.time()))
        logger.debug("Added customer audio segment: %d bytes", len(audio_data))

    async def receive_messages(self) -> None:
        """Receive and process messages from the WebSocket."""
        if not self.websocket:
            raise RuntimeError("Not connected")

        async for message in self.websocket:
            data = json.loads(message)
            if data.get("kind") == "AudioData":

                if not self.current_assistant_turn_started_at:
                    self.current_assistant_turn_started_at = time.time()

                # Received assistant audio
                audio_b64 = data["audioData"]["data"]
                audio_data = base64.b64decode(audio_b64)

                now = time.time()

                # NEW: if this is the first chunk of a new assistant turn, record the start time
                #if not self.is_assistant_speaking and len(self.current_assistant_audio) == 0:
                #    self.current_assistant_turn_started_at = now

                self.audio_buffer.extend(audio_data)
                self.current_assistant_audio.extend(audio_data)

                self.last_audio_received_time = now
                self.last_assistant_activity_time = now
                self.is_assistant_speaking = True

                logger.debug("Received assistant audio: %d bytes", len(audio_data))
            elif data.get("kind") == "ChatHistory":
                new_messages = data.get("data", [])
                self.chat_history.extend(new_messages)
            else:
                logger.debug("Received message: %s", data)

    # NEW: Non-mutating accessor
    def get_current_assistant_turn(
        self,
    ) -> Optional[Tuple[bytes, Optional[float], Optional[float]]]:
        """
        Return a snapshot of the in-progress assistant turn *without* mutating state.

        Returns:
            None if no audio is currently buffered for the assistant; otherwise:
            (audio_bytes, started_at_epoch_seconds, last_activity_epoch_seconds)
        """
        if not self.current_assistant_audio:
            return None

        # bytes(...) makes a copy so callers cannot mutate our internal buffer
        return (
            bytes(self.current_assistant_audio),
            self.current_assistant_turn_started_at,
            self.last_assistant_activity_time,
        )
    
    async def wait_for_assistant_to_start_speaking(
        self,
        timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.3,
    ) -> None:
        """
        Wait until the assistant starts speaking (receives first audio).
        """
        start_time = time.time()
        initial_audio_time = self.last_audio_received_time
        
        logger.debug("Waiting for assistant to start speaking...")
        
        while True:
            now = time.time()
            
            # Check if we've received new audio since we started waiting
            if self.last_audio_received_time and (
                initial_audio_time is None or self.last_audio_received_time > initial_audio_time
            ):
                logger.info("Assistant started speaking.")
                return
                
            # Timeout check
            if now - start_time >= timeout_seconds:
                logger.warning("Timeout waiting for assistant to start speaking (%.1fs).", timeout_seconds)
                return
                
            await asyncio.sleep(poll_interval_seconds)

    async def wait_for_assistant_turn_end(
        self,
        silence_threshold_seconds: float = 4,
        timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.3,
    ) -> None:
        """
        Wait until the assistant has stopped speaking, defined as either:
          1) `silence_threshold_seconds` of no audio after speech has begun, or
          2) `timeout_seconds` total since this call started.
        On end, flushes the buffered assistant audio into `conversation_segments`.
        """
        start_time = time.time()
        initial_wait = True

        logger.debug(
            "Waiting for assistant turn end (silence=%.1fs, timeout=%.1fs)...",
            silence_threshold_seconds,
            timeout_seconds,
        )

        while True:
            now = time.time()

            # We have received some audio since we started waiting; disable "initial wait"
            if self.last_audio_received_time and self.last_audio_received_time > start_time:
                initial_wait = False

            # Silence detection only after we have received audio
            if self.last_audio_received_time and not initial_wait:
                gap = now - self.last_audio_received_time
                if gap >= silence_threshold_seconds:
                    if self.current_assistant_audio:
                        self.conversation_segments.append(
                            ("assistant", bytes(self.current_assistant_audio), time.time())
                        )
                        logger.debug(
                            "Saved assistant turn: %d bytes", len(self.current_assistant_audio)
                        )
                        self.current_assistant_audio = bytearray()
                        self.is_assistant_speaking = False
                        # NEW: clear start marker after flushing the turn
                        self.current_assistant_turn_started_at = None
                    logger.info("Assistant finished speaking (%.1fs silence).", gap)
                    break

            # Overall timeout
            if now - start_time >= timeout_seconds:
                logger.warning("Timeout waiting for assistant (%.1fs).", timeout_seconds)
                if self.current_assistant_audio:
                    self.conversation_segments.append(
                        ("assistant", bytes(self.current_assistant_audio), time.time())
                    )
                    logger.debug(
                        "Saved assistant turn on timeout: %d bytes",
                        len(self.current_assistant_audio),
                    )
                    self.current_assistant_audio = bytearray()
                    self.current_assistant_turn_started_at = None
                self.is_assistant_speaking = False
                break

            await asyncio.sleep(poll_interval_seconds)  # or: await asyncio.sleep(...)

    async def disconnect(self) -> None:
        """Flush any remaining assistant audio and close the WebSocket."""
        # Flush pending assistant segment into the timeline
        if self.current_assistant_audio:
            self.conversation_segments.append(
                ("assistant", bytes(self.current_assistant_audio), time.time())
            )
            logger.debug(
                "Saved final assistant segment: %d bytes", len(self.current_assistant_audio)
            )
            self.current_assistant_audio = bytearray()
            self.current_assistant_turn_started_at = None
            self.is_assistant_speaking = False

        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("Disconnected")
            finally:
                self.websocket = None

    async def save_conversation_audio(self, output_path: str) -> None:
        """Save the complete conversation (both sides) to a single WAV file."""
        if not self.conversation_segments:
            logger.warning("No conversation to save")
            return

        combined_audio = bytearray()

        logger.info("Conversation timeline (%d segments):", len(self.conversation_segments))
        for idx, (role, audio_data, _ts) in enumerate(self.conversation_segments, start=1):
            duration_ms = len(audio_data) / (SAMPLE_RATE_HZ * SAMPLE_WIDTH_BYTES) * 1000.0
            logger.info("  %2d. %-9s: %6.0f ms", idx, role.capitalize(), duration_ms)
            combined_audio.extend(audio_data)

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav_file.setframerate(SAMPLE_RATE_HZ)
            wav_file.writeframes(combined_audio)

        logger.info("Saved complete conversation to %s", output_path)
