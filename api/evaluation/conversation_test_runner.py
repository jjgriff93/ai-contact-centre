import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv_azd import load_azd_env
from evaluation.utils import (ask_proxy_human, speech_to_text_pcm,
                              text_to_speech_pcm)
from evaluation.voice_call_client import VoiceCallClient
from openai import AsyncAzureOpenAI

# -----------------------------------------------------------------------------
# Configuration & logging
# -----------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables from azd .env file
load_azd_env()

AZURE_AI_SERVICES_ENDPOINT = os.getenv("AZURE_AI_SERVICES_ENDPOINT")

if not AZURE_AI_SERVICES_ENDPOINT:
    raise ValueError("AZURE_AI_SERVICES_ENDPOINT environment variable is not set.")

# Audio constants (keep in one place)
SAMPLE_RATE_HZ = 24_000
SAMPLE_WIDTH_BYTES = 2  # 16-bit
CHANNELS = 1

# -----------------------------------------------------------------------------
# Azure OpenAI client (consider dependency injection for testability)
# -----------------------------------------------------------------------------
token_provider = get_bearer_token_provider(
    DefaultAzureCredential(exclude_managed_identity_credential=True),
    "https://cognitiveservices.azure.com/.default",
)

aoai_client = AsyncAzureOpenAI(
    azure_endpoint=AZURE_AI_SERVICES_ENDPOINT,
    azure_ad_token_provider=token_provider,
    api_version="2024-02-15-preview",
)

# -----------------------------------------------------------------------------
# Types & state
# -----------------------------------------------------------------------------

MessageRole = Literal["assistant", "user"]


@dataclass
class AudioState:
    """
    Collects raw audio from both sides for later export or analysis.
    """
    assistant_chunks: List[bytes] = field(default_factory=list)
    proxy_chunks: List[bytes] = field(default_factory=list)
    combined_chunks: List[bytes] = field(default_factory=list)

    def add_assistant(self, data: bytes) -> None:
        self.assistant_chunks.append(data)
        self.combined_chunks.append(data)

    def add_proxy(self, data: bytes) -> None:
        self.proxy_chunks.append(data)
        self.combined_chunks.append(data)


@dataclass
class TurnTiming:
    """Tracks timing information for a single turn."""
    role: MessageRole
    start_time: float
    end_time: float
    duration: float
    content: str
    
    def to_dict(self) -> Dict[str, object]:
        return {
            "role": self.role,
            "start_time": self.start_time,
            "start_datetime": datetime.fromtimestamp(self.start_time).isoformat(timespec="milliseconds"),
            "end_time": self.end_time,
            "end_datetime": datetime.fromtimestamp(self.end_time).isoformat(timespec="milliseconds"),
            "duration_seconds": self.duration,
            "content": self.content
        }
    

@dataclass
class ConversationState:
    """
    Holds transcript/history and last-activity tracking for the test run.
    Raw audio is delegated to AudioState.
    """
    history: List[Dict[str, object]] = field(default_factory=list)
    last_activity_ts: float = field(default_factory=time.time)
    audio: AudioState = field(default_factory=AudioState)
    turn_timings: List[TurnTiming] = field(default_factory=list)  # Add this

    def append_message(self, role: MessageRole, content: str, activity_ts: Optional[float] = None, 
                      start_time: Optional[float] = None, end_time: Optional[float] = None) -> None:

        now = time.time()
        entry = {
            "role": role,
            "content": content,
            "datetime": datetime.fromtimestamp(now).isoformat(timespec="milliseconds"),
            "activity_datetime": (
                datetime.fromtimestamp(activity_ts).isoformat(timespec="milliseconds") if activity_ts else None
            ),
            "start_datetime": datetime.fromtimestamp(start_time).isoformat(timespec="milliseconds") if start_time else None,
            "end_datetime": datetime.fromtimestamp(end_time).isoformat(timespec="milliseconds") if end_time else None,
            "duration_seconds": (end_time - start_time) if start_time and end_time else None
   
        }
        self.history.append(entry)
        self.last_activity_ts = now

    def timed_out(self, threshold_seconds: float = 10.0) -> bool:
        return (time.time() - self.last_activity_ts) > threshold_seconds


async def send_text_to_server(harness: VoiceCallClient, text: str) -> bytes:
    """
    TTS the provided text and stream PCM chunks to the server via the harness.
    A short silence tail is appended to reliably trigger VAD on the server.
    Returns the PCM bytes that were sent (including trailing silence).
    """

    start_time = time.time()
    
    audio = bytearray()
    async for pcm_chunk in text_to_speech_pcm(aoai_client, text):
        audio.extend(pcm_chunk)
        await harness.send_audio_chunk(pcm_chunk)

    silence_ms = 1000
    silence_frames = int((SAMPLE_RATE_HZ * silence_ms) / 1000)
    post_silence = b"\x00" * (silence_frames * SAMPLE_WIDTH_BYTES)
    audio.extend(post_silence)
    await harness.send_audio_chunk(post_silence)

    end_time = time.time()

    logger.debug("Sent TTS audio (%d bytes) + %dms silence.", len(audio) - len(post_silence), silence_ms)

    return bytes(audio), start_time, end_time


class TestScenario:
    """Base class for test scenarios."""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    async def run(self, harness: VoiceCallClient, state: ConversationState) -> None:
        """Run the test scenario."""
        raise NotImplementedError


class ProxyHumanScenario(TestScenario):
    """Test scenario for proxy human interaction."""

    def __init__(self, system_prompt: Optional[str] = None) -> None:
        super().__init__(
            "Proxy Human Interaction",
            "Agent simulates a human customer interacting with the voice AI system.",
        )
        self.system_prompt = system_prompt or (
            "You are a grocery shopper talking on the phone to a customer support agent. "
            "Say hello at the beginning of the conversation. You want to buy two Fuji apples and have it delivered "
            "on Wed 23rd at 4pm. Stay in role, never change from grocery shopper. Your questions and responses must "
            "be very short. When you are done say 'goodbye'. "
            "Your address is 21 Baker Street, London but only say it when asked."
        )

    async def run(self, harness: VoiceCallClient, state: ConversationState) -> None:
        EXIT_TERMS = {"exit", "goodbye", "bye", "quit", "stop"}

        logger.info("Waiting for assistant greeting...")
        assistant_start_time = time.time()
        await harness.wait_for_assistant_to_start_speaking(timeout_seconds=10)
        await harness.wait_for_assistant_turn_end()
        assistant_end_time = time.time()
        logger.info("Assistant greeting received.")

        # Transcribe latest assistant segment, if available
        last_assistant = next(
            (seg for seg in reversed(harness.conversation_segments) if seg[0] == "assistant"),
            None,
        )
        if last_assistant:
            assistant_audio = last_assistant[1]
            assistant_text = await speech_to_text_pcm(aoai_client, assistant_audio)
            logger.info("Start ==== Assistant: %s", assistant_text)
            state.audio.add_assistant(assistant_audio)
            state.append_message("assistant", assistant_text, harness.last_assistant_activity_time,
                            start_time=harness.current_assistant_turn_started_at or assistant_start_time,
                            end_time=assistant_end_time)
        
        # Conversation loop
        conversation_turns = 0
        max_turns = 8  # prevent infinite loops

        while conversation_turns < max_turns:
            conversation_turns += 1

            logger.info("Generating customer response...")
            customer_response = await ask_proxy_human(aoai_client, state.history, self.system_prompt)
            logger.info("Customer: %s", customer_response)

            # Send response audio
            customer_audio, customer_start_time, customer_end_time = await send_text_to_server(harness, customer_response)
            harness.add_customer_audio(customer_audio)
            state.audio.add_proxy(customer_audio)
            state.append_message("user", customer_response, time.time(), 
                            start_time=customer_start_time,
                            end_time=customer_end_time)
            
            # Exit condition
            if any(term in customer_response.lower() for term in EXIT_TERMS):
                logger.info("Customer said goodbye; ending conversation.")
                break

            # Await and transcribe assistant reply
            assistant_start_time = time.time()

            await harness.wait_for_assistant_turn_end()

            assistant_end_time = time.time()

            last_assistant = next(
                (seg for seg in reversed(harness.conversation_segments) if seg[0] == "assistant"),
                None,
            )
            if last_assistant:
                assistant_audio = last_assistant[1]
                assistant_text = await speech_to_text_pcm(aoai_client, assistant_audio)
                logger.info("Assistant: %s", assistant_text)
                state.audio.add_assistant(assistant_audio)
                state.append_message("assistant", assistant_text, harness.last_assistant_activity_time,
                                    start_time=harness.current_assistant_turn_started_at or assistant_start_time,
                                    end_time=assistant_end_time)

        logger.info("Conversation completed after %d turns.", conversation_turns)

        # Summary with timing information
        logger.info("Conversation Summary with Timing:")
        for timing in state.turn_timings:
            role = "Customer" if timing.role == "user" else "Assistant"
            logger.info("%s | %s | Duration: %.2fs | %s", 
                    datetime.fromtimestamp(timing.start_time).strftime("%H:%M:%S.%f")[:-3],
                    role, 
                    timing.duration,
                    timing.content)

        self.output_transcript(state)
            
    def output_transcript(self, state: ConversationState) -> None:
        """
        Save the conversation history to a JSON file.
        """
       # Output the full transcript as a multiline string
        transcript_lines = ["\n" + "="*60, "FULL CONVERSATION TRANSCRIPT", "="*60]
        
        for msg in state.history:
            role = "Customer" if msg["role"] == "user" else "Assistant"
            timestamp = msg.get("start_datetime", msg.get("datetime", ""))
            
            # Format each line of the transcript
            if timestamp:
                # Extract just the time portion if it's a full datetime
                if "T" in timestamp:
                    time_part = timestamp.split("T")[1].split(".")[0]  # Gets HH:MM:SS
                else:
                    time_part = timestamp
                transcript_lines.append(f"[{time_part}] {role}: {msg['content']}")
            else:
                transcript_lines.append(f"{role}: {msg['content']}")
        
        transcript_lines.append("="*60)
        
        # Log the complete transcript as one multiline string
        logger.info("\n".join(transcript_lines))


async def run_test_suite() -> None:
    """Run a suite of test scenarios."""
    scenarios: List[TestScenario] = [
        ProxyHumanScenario(),
    ]

    for scenario in scenarios:
        banner = "=" * 50
        logger.info("\n%s\nRunning: %s\nDescription: %s\n%s", banner, scenario.name, scenario.description, banner)

        harness = VoiceCallClient()
        state = ConversationState()
        receive_task: Optional[asyncio.Task] = None

        try:
            await harness.connect(f"test-{scenario.name.replace(' ', '_')}")
            receive_task = asyncio.create_task(harness.receive_messages())

            await scenario.run(harness, state)

            # Give the server a moment to finish any trailing work
            await asyncio.sleep(3)

            # Save outputs
            output_dir = Path("test_outputs")
            output_dir.mkdir(exist_ok=True)

            wav_path = output_dir / f"{scenario.name.replace(' ', '_')}_conversation.wav"
            await harness.save_conversation_audio(str(wav_path))

            transcript_path = output_dir / f"{scenario.name.replace(' ', '_')}_transcript.json"
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(state.history, f, indent=2, ensure_ascii=False)
            logger.info("Transcript saved to %s", transcript_path)

        finally:
            if receive_task:
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass
            await harness.disconnect()


if __name__ == "__main__":
    asyncio.run(run_test_suite())
