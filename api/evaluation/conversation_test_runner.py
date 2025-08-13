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
from azure.ai.evaluation import evaluate
from dotenv_azd import load_azd_env
from openai import AsyncAzureOpenAI

from evaluation.utils import (ask_proxy_human, speech_to_text_pcm,
                              text_to_speech_pcm,
                              convert_json_to_jsonl)
from evaluation.voice_call_client import VoiceCallClient
from evaluation.metrics import FunctionCallEvaluator, ConversationEvaluator


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
            "content": self.content,
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
    function_calls: List[Dict[str, object]] = field(default_factory=list)

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
            "duration_seconds": (end_time - start_time) if start_time and end_time else None,
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


class ProxyHumanConversator:
    """Test scenario for proxy human interaction that serves as an evaluation target."""

    def __init__(self, output_dir: str, max_turns: int = 8) -> None:
        self.output_dir = output_dir
        self.max_turns = max_turns
        self.EXIT_TERMS = {"exit", "goodbye", "bye", "quit", "stop"}

    def __call__(self, *, scenario_name: str, instructions: str, **kwargs) -> Dict[str, object]:
        """
        This method simulates a call center conversation
        by interacting with the voice AI system and generating user responses.
        This is used as "Evaluation Target" by the evaluation framework.

        Args:
            instructions (str): instructions for the simulated user

        Returns:
            Dict[str, object]: conversation results including history and function calls
        """
        # Run the conversation
        state = asyncio.run(self._run_conversation(scenario_name, instructions))

        # Return outputs for evaluation
        return {
            "function_calls": state.function_calls,
            "transcription": state.history,
        }

    async def _run_conversation(self, scenario_name: str, scenario_instructions: str) -> Dict[str, object]:
        """Run the conversation and return final state."""

        harness = VoiceCallClient()
        state = ConversationState()
        receive_task: Optional[asyncio.Task] = None

        try:
            await harness.connect(f"test-evaluation-{int(time.time())}")
            receive_task = asyncio.create_task(harness.receive_messages())

            # Run the conversation
            conversation_turn = 0
            while conversation_turn < self.max_turns:
                # Await and transcribe assistant reply
                assistant_start_time = time.time()
                if conversation_turn == 0:
                    logger.info("Waiting for assistant greeting...")
                    await harness.wait_for_assistant_to_start_speaking(timeout_seconds=10)
                await harness.wait_for_assistant_turn_end()
                assistant_end_time = time.time()
                logger.info("Assistant message received.")

                last_assistant = next(
                    (seg for seg in reversed(harness.conversation_segments) if seg[0] == "assistant"),
                    None,
                )
                if last_assistant:
                    logger.info("Processing assistant message...")
                    assistant_audio = last_assistant[1]
                    assistant_text = await speech_to_text_pcm(aoai_client, assistant_audio)
                    logger.info("Assistant: %s", assistant_text)
                    state.audio.add_assistant(assistant_audio)
                    state.append_message("assistant", assistant_text, harness.last_assistant_activity_time,
                                         start_time=harness.current_assistant_turn_started_at or assistant_start_time,
                                         end_time=assistant_end_time)

                logger.info("Generating customer response...")
                customer_response = await ask_proxy_human(aoai_client, state.history, scenario_instructions)
                logger.info("Customer: %s", customer_response)

                # Send response audio
                customer_audio, customer_start_time, customer_end_time = await send_text_to_server(harness, customer_response)
                harness.add_customer_audio(customer_audio)
                state.audio.add_proxy(customer_audio)
                state.append_message("user", customer_response, time.time(),
                                     start_time=customer_start_time,
                                     end_time=customer_end_time)

                conversation_turn += 1

                # Exit condition
                if any(term in customer_response.lower() for term in self.EXIT_TERMS):
                    logger.info("Customer said goodbye; ending conversation.")
                    break

            logger.info("Conversation completed after %d turns.", conversation_turn)

            # Give the server a moment to finish any trailing work
            await asyncio.sleep(3)

            # Extract function calls from chat history
            state.function_calls = self._get_function_calls_from_chat_history(harness.chat_history)

            # Store results and output transcript summary 
            wav_path = self.output_dir / f"{scenario_name}_conversation.wav"
            await harness.save_conversation_audio(str(wav_path))

            transcript_path = self.output_dir / f"{scenario_name}_transcript.json"
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(state.history, f, indent=2, ensure_ascii=False)
            logger.info("Transcript saved to %s", transcript_path)

            self._output_transcript(scenario_name, state)

        finally:
            if receive_task:
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass
            await harness.disconnect()

        return state

    def _get_function_calls_from_chat_history(self, chat_history: List[Dict[str, object]]) -> List[Dict[str, object]]:
        """Extract function calls from the chat history exported from Semantic Kernel app."""
        return [fcall for msg in chat_history if msg["role"] == "tool" for fcall in msg["function_calls"]]

    def _output_transcript(self, scenario_name: str, state: ConversationState) -> None:
        """
        Print a summary of the conversation history
        """
        # Output the full transcript as a multiline string
        transcript_lines = ["\n" + "=" * 60, f"SCENARIO: {scenario_name} ", "FULL CONVERSATION TRANSCRIPT", "=" * 60]

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

        transcript_lines.append("=" * 60)

        # Log the complete transcript as one multiline string
        logger.info("\n".join(transcript_lines))


def run_test_suite(azure_ai_project_endpoint: str) -> None:
    """Run a suite of test scenarios using the evaluate() method."""

    testcases_dir = Path(__file__).parent / "testcases"
    output_dir = testcases_dir / "test_outputs"
    output_dir.mkdir(exist_ok=True)

    # Prepare test cases - evaluation framework expects jsonl format
    eval_data_path = str(testcases_dir / "eval_dataset.json")
    eval_jsonl_path = convert_json_to_jsonl(eval_data_path)

    # Run evaluation across all test cases
    evaluation_name = f"conversation-tests-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    # os.environ["PF_WORKER_COUNT"] = "1"  # Max concurrency for eval target run  #TODO: useful?
    result = evaluate(
        evaluation_name=evaluation_name,
        data=eval_jsonl_path,
        target=ProxyHumanConversator(max_turns=8, output_dir=output_dir),
        evaluators={
            "function_calls": FunctionCallEvaluator(),
            "conversation": ConversationEvaluator()
        },
        evaluator_config={
            "default": {
                "column_mapping": {
                    "scenario_name": "${data.scenario_name}",
                    "instructions": "${data.instructions}",
                    "function_calls": "${target.function_calls}",
                    "transcription": "${target.transcription}",
                    "expected_function_calls": "${data.expected_function_calls}",
                    "unexpected_function_calls": "${data.unexpected_function_calls}"
                }
            },
        },
        azure_ai_project=azure_ai_project_endpoint,
        output_path=output_dir / f"eval_results_{evaluation_name}.json",
    )

    logger.info("Evaluation completed. Summary: %s", result)


if __name__ == "__main__":

    try:
        azure_ai_project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    except KeyError as e:
        raise ValueError(f"Missing environment variable: {e}") from e

    run_test_suite(azure_ai_project_endpoint)
