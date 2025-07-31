import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from azure.identity import DefaultAzureCredential
from dotenv_azd import load_azd_env
from evaluation.utils import (ask_proxy_human, speech_to_text_pcm,
                              text_to_speech_pcm)
from evaluation.voice_call_client import VoiceCallClient
from openai import AsyncAzureOpenAI

# Load environment variables from azd .env file
load_azd_env()

AZURE_AI_SERVICES_ENDPOINT = os.getenv("AZURE_AI_SERVICES_ENDPOINT")
AZURE_CHAT_DEPLOYMENT_TEXT = os.getenv("AZURE_CHAT_MODEL_DEPLOYMENT_NAME")
AZURE_TTS_DEPLOYMENT = os.getenv("AZURE_TTS_MODEL_DEPLOYMENT_NAME")

if not AZURE_AI_SERVICES_ENDPOINT:
    raise ValueError("AZURE_AI_SERVICES_ENDPOINT environment variable is not set.")

if not AZURE_CHAT_DEPLOYMENT_TEXT:
    raise ValueError("AZURE_CHAT_MODEL_DEPLOYMENT_NAME environment variable is not set.")

if not AZURE_TTS_DEPLOYMENT:
    raise ValueError("AZURE_TTS_MODEL_DEPLOYMENT_NAME environment variable is not set.")

from azure.identity import DefaultAzureCredential, get_bearer_token_provider

tokenProvider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default",
)


aoai_client = AsyncAzureOpenAI(
    azure_endpoint=AZURE_AI_SERVICES_ENDPOINT,
    azure_ad_token_provider=tokenProvider,
    api_version="2024-02-15-preview",
)


async def wait_for_assistant_to_finish(harness: VoiceCallClient, timeout: float = 10.0):
    """Wait for assistant to finish speaking with timeout detection."""
    start_time = time.time()
    initial_wait = True
    
    THRESHOLD = 4.0  # seconds of silence to consider assistant finished

    while True:
        current_time = time.time()
        
        # Once we receive any audio, we're no longer in initial wait
        if harness.last_audio_received_time and harness.last_audio_received_time > start_time:
            initial_wait = False

        # Check if we haven't received audio for a while
        if harness.last_audio_received_time and not initial_wait:
            time_since_audio = current_time - harness.last_audio_received_time
            if time_since_audio >= THRESHOLD:  # 2 seconds of no audio
                # Save assistant audio when silence is detected
                if harness.current_assistant_audio:
                    harness.conversation_segments.append(
                        ("assistant", bytes(harness.current_assistant_audio), time.time())
                    )
                    print(f"Saved assistant turn: {len(harness.current_assistant_audio)} bytes")
                    harness.current_assistant_audio = bytearray()
                    harness.is_assistant_speaking = False
                print(f"Assistant finished (silent for {time_since_audio:.1f}s)")
                break
                
        # Overall timeout
        if current_time - start_time >= timeout:
            print("Timeout waiting for assistant")
            # Save any pending audio
            if harness.current_assistant_audio:
                harness.conversation_segments.append(
                    ("assistant", bytes(harness.current_assistant_audio), time.time())
                )
                print(f"Saved assistant turn on timeout: {len(harness.current_assistant_audio)} bytes")
                harness.current_assistant_audio = bytearray()
            break
            
        await asyncio.sleep(0.1)



class ConversationState:
    """Manages conversation state between proxy human and backend."""
    
    def __init__(self):
        self.history: List[Dict[str, str]] = []
        self.assistant_audio_chunks: List[bytes] = []
        self.proxy_audio_chunks: List[bytes] = []
        self.combined_audio_chunks: List[bytes] = []
        self.last_activity = time.time()
        self.current_transcript = ""
        
    def append_message(self, role: str, content: str, timestamp: float = None):
        ts = time.time()
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")
        last_activity_datetime = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")
        self.history.append({"role": role, "content": content, "timestamp": time.time(), "datetime": dt, "last_activity": last_activity_datetime})
        
    def add_assistant_audio(self, audio_data: str):
        self.assistant_audio_chunks.append(audio_data)
        self.combined_audio_chunks.append(audio_data)
    
    def add_proxy_audio(self, audio_data: str):
        self.proxy_audio_chunks.append(audio_data)
        self.combined_audio_chunks.append(audio_data)
        
    def update_activity(self):
        self.last_activity = time.time()
        
    @property
    def timed_out(self) -> bool:
        return time.time() - self.last_activity > 10



async def send_text_to_server(harness: VoiceCallClient, text: str) -> bytes:
    audio = bytearray()
    async for pcm_chunk in text_to_speech_pcm(aoai_client, AZURE_TTS_DEPLOYMENT, text):
        audio.extend(pcm_chunk)
        await harness.send_audio_chunk(pcm_chunk)
    
    # Send silence to trigger VAD
    post_silence = b'\x00' * (24000 * 2)  # 1 second of silence, 24KHz (24000 samples), 16-bit mono (2 bytes per sample)
    audio.extend(post_silence)
    await harness.send_audio_chunk(post_silence)

    return audio


class TestScenario:
    """Base class for test scenarios."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        
    async def run(self, harness: VoiceCallClient):
        """Run the test scenario."""
        raise NotImplementedError
        

class ProxyHumanScenario(TestScenario):
    """Test scenario for proxy human interaction."""

    def __init__(self, system_prompt: str = None):
        super().__init__(
            "Proxy Human Interaction",
            "Agent simulates a human customer interacting with the voice AI system."
        )
        self.system_prompt = system_prompt or (
            "You are a grocery shopper talking on the phone to a customer support agent. "
            "Say hello at the beginning of the conversation. You want to buy two Fuji apples and have it delivered "
            "on Wed 23rd at 4pm. Stay in role, never change from grocery shopper. Your questions and responses must "
            "be very short. When you are done say 'goodbye'. "
            "Your address is 21 Baker Street, London but only say it when asked."
        )
    
    async def run(self, harness: VoiceCallClient, state: ConversationState):

        EXIT_TERMS = {"exit", "goodbye", "bye", "quit", "stop"}

        # Wait for greeting and transcribe it
        print("⏳ Waiting for assistant greeting...")
        await wait_for_assistant_to_finish(harness)
        
        # Transcribe assistant's greeting
        if harness.conversation_segments:
            # Get the last assistant segment
            last_segment = harness.conversation_segments[-1]
            if last_segment[0] == "assistant":
                assistant_text = await speech_to_text_pcm(aoai_client, last_segment[1])
                print(f"🤖 Assistant: {assistant_text}")
                state.add_assistant_audio(last_segment[1])
                state.append_message("assistant", assistant_text, harness.last_assistant_activity_time)
        
        # Continue conversation until goodbye
        conversation_turns = 0
        max_turns = 8  # Prevent infinite loops
        
        while conversation_turns < max_turns:
            conversation_turns += 1
            
            # Get proxy human response
            print("\nGenerating customer response...")
            customer_response = await ask_proxy_human(aoai_client, AZURE_CHAT_DEPLOYMENT_TEXT, state.history, self.system_prompt)
            print(f"Customer: {customer_response}")
            
            # Check if conversation should end
            if any(term in customer_response.lower() for term in EXIT_TERMS):
                print("Customer said goodbye, ending conversation")

                # Send the goodbye message
                customer_audio = await send_text_to_server(harness, customer_response)
                state.add_proxy_audio(customer_audio)
                harness.add_customer_audio(bytes(customer_audio))
                state.append_message("user", customer_response, time.time())
                break
            
            # Convert customer response to speech and send
            customer_audio = await send_text_to_server(harness, customer_response)            
            # Save customer audio and update state
            harness.add_customer_audio(bytes(customer_audio))
            state.add_proxy_audio(customer_audio)
            state.append_message("user", customer_response, time.time())
            
            # Wait for assistant response
            await wait_for_assistant_to_finish(harness)
            
            # Transcribe assistant's response
            if len(harness.conversation_segments) > conversation_turns * 2:
                # Get the latest assistant segment
                for i in range(len(harness.conversation_segments) - 1, -1, -1):
                    if harness.conversation_segments[i][0] == "assistant":
                        assistant_audio = harness.conversation_segments[i][1]
                        assistant_text = await speech_to_text_pcm(aoai_client, assistant_audio)
                        print(f"🤖 Assistant: {assistant_text}")
                        state.add_assistant_audio(assistant_audio)
                        state.append_message("assistant", assistant_text, harness.last_assistant_activity_time)
                        break
        
        print(f"\nConversation completed after {conversation_turns} turns")
        
        # Print conversation summary
        print("\nConversation Summary:")
        for msg in state.history:
            role = "Customer" if msg["role"] == "user" else "Assistant"
            print(f"{msg["timestamp"]}  {role}: {msg['content']}")


async def run_test_suite():
    """Run a suite of test scenarios."""
    scenarios = [
        # Add more scenarios here
        ProxyHumanScenario()
    ]
    
    for scenario in scenarios:
        print(f"\n{'='*50}")
        print(f"Running: {scenario.name}")
        print(f"Description: {scenario.description}")
        print(f"{'='*50}\n")
        
        harness = VoiceCallClient()
        state = ConversationState()
        try:
            await harness.connect(f"test-{scenario.name}")
            
            receive_task = asyncio.create_task(harness.receive_messages())
            await scenario.run(harness, state)
            await asyncio.sleep(3)  # Wait for any final responses
            
            # Save the conversation audio
            output_dir = Path("test_outputs")
            output_dir.mkdir(exist_ok=True)
            
            # Save the complete conversation as one file
            await harness.save_conversation_audio(
                f"test_outputs/{scenario.name.replace(' ', '_')}_conversation.wav"
            )

            # Also save conversation transcript
            if isinstance(scenario, ProxyHumanScenario):
                transcript_path = f"test_outputs/{scenario.name.replace(' ', '_')}_transcript.json"
                with open(transcript_path, "w") as f:
                    json.dump(state.history, f, indent=4)  # Save the history as a JSON file
                print(f"Transcript saved to {transcript_path}")

        finally:
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass
            await harness.disconnect()
            

if __name__ == "__main__":
    asyncio.run(run_test_suite())
