import asyncio
import base64
import json
import logging
import wave
import websockets
from typing import Optional
import numpy as np
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VoiceCallClient:
    """Test harness for simulating ACS calls to the voice AI system."""
    
    def __init__(self, websocket_url: str = "ws://localhost:8000/ws"):
        self.websocket_url = websocket_url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.audio_buffer = bytearray()
        self.customer_audio_buffer = bytearray()  # Customer audio only
        self.conversation_segments = []  # List of (role, audio_data, timestamp) tuples
        self.last_audio_received_time = None
        self.current_assistant_audio = bytearray()  # Buffer for current assistant turn
        self.is_assistant_speaking = False
        self.last_assistant_activity_time = None
  
      
    async def connect(self, call_connection_id: str = "test-connection-123"):
        """Connect to the WebSocket endpoint with required headers."""
        headers = {
            "x-ms-call-connection-id": call_connection_id
        }
        self.websocket = await websockets.connect(
            self.websocket_url,
            additional_headers=headers  # Changed from extra_headers
        )
        logger.info(f"Connected to {self.websocket_url}")

        
    async def send_audio_chunk(self, audio_data: bytes):
        """Send an audio chunk to the WebSocket."""
        if not self.websocket:
            raise RuntimeError("Not connected")
            
        message = {
            "kind": "AudioData",
            "audioData": {
                "data": base64.b64encode(audio_data).decode("utf-8")
            }
        }
        await self.websocket.send(json.dumps(message))
  
    def add_customer_audio(self, audio_data: bytes):
        """Add customer audio to the conversation."""
        self.customer_audio_buffer.extend(audio_data)
        self.conversation_segments.append(("customer", audio_data, time.time()))
        logger.info(f"Added customer audio segment: {len(audio_data)} bytes")

    async def receive_messages(self):
        """Receive and process messages from the WebSocket."""
        if not self.websocket:
            raise RuntimeError("Not connected")
            
        async for message in self.websocket:
            data = json.loads(message)
            
            if data.get("kind") == "AudioData":
                # Received audio from the AI
                audio_data = base64.b64decode(data["audioData"]["data"])
                self.audio_buffer.extend(audio_data)
                self.current_assistant_audio.extend(audio_data)
                self.last_audio_received_time = time.time()
                self.last_assistant_activity_time = time.time()
                self.is_assistant_speaking = True
                logger.info(f"Received {len(audio_data)} bytes of audio")
                
            else:
                logger.info(f"Received message: {data}")

    async def disconnect(self):
        """Disconnect from the WebSocket."""
        # Save any remaining assistant audio
        if self.current_assistant_audio:
            self.conversation_segments.append(
                ("assistant", bytes(self.current_assistant_audio), time.time())
            )
            logger.info(f"Saved final assistant segment: {len(self.current_assistant_audio)} bytes")
            self.current_assistant_audio = bytearray()
            
        if self.websocket:
            await self.websocket.close()
            logger.info("Disconnected")

    async def save_conversation_audio(self, output_path: str):
        """Save the complete conversation (both sides) to a WAV file."""
        if not self.conversation_segments:
            logger.warning("No conversation to save")
            return
            
        # Combine all audio segments in order
        combined_audio = bytearray()
        
        print("\nConversation timeline:")
        for i, (role, audio_data, timestamp) in enumerate(self.conversation_segments):
            duration_ms = len(audio_data) / (24000 * 2) * 1000  # 24kHz, 16-bit
            print(f"  {i+1}. {role.capitalize()}: {duration_ms:.0f}ms of audio")
            combined_audio.extend(audio_data)
            
        # Save combined audio
        with wave.open(output_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(24000)  # 24kHz
            wav_file.writeframes(combined_audio)
            
        logger.info(f"Saved complete conversation to {output_path}")
