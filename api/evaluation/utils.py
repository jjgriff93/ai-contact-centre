import io
import os
from openai import AsyncAzureOpenAI
import wave
from typing import List
from dotenv import load_dotenv

load_dotenv()


AZURE_CHAT_DEPLOYMENT_TEXT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
AZURE_TTS_DEPLOYMENT = os.getenv("AZURE_OPENAI_TTS_DEPLOYMENT")


async def speech_to_text_pcm(client: AsyncAzureOpenAI, audio_data: bytes) -> str:
    """Convert PCM audio to text using Azure OpenAI (gpt-4o-mini-transcribe) directly from bytes."""
     # Build a WAV file in-memory from the raw PCM
    wav_bytes = io.BytesIO()
    # PCM: 24kHz, 16-bit, mono, little-endian
    with wave.open(wav_bytes, "wb") as wf:
        wf.setnchannels(1)  # mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(24000)  # 24KHz
        wf.writeframes(audio_data)  # no copy; writes directly from your PCM buffer
    wav_bytes.seek(0)
    
    file_tuple = ("audio.wav", wav_bytes, "audio/wav")

    response = await client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=file_tuple,
        response_format="text",
    )
    return response.strip() if response else ""


async def text_to_speech_pcm(client: AsyncAzureOpenAI, text: str, chunk_size: int = 100):
    """Convert text to PCM audio chunks."""
    
    bytes_per_chunk = 9600 #PCM_RATE * 2 * chunk_size // 1000  # 16-bit PCM
    buffer = b""
    
    async with client.audio.speech.with_streaming_response.create(
        model=AZURE_TTS_DEPLOYMENT,
        voice="fable",
        input=text,
        response_format="pcm"  # Raw 16-bit PCM
    ) as response:
        async for chunk in response.iter_bytes():
            buffer += chunk
            while len(buffer) >= bytes_per_chunk:
                yield buffer[:bytes_per_chunk]
                buffer = buffer[bytes_per_chunk:]
        if buffer:
            yield buffer


async def ask_proxy_human(client: AsyncAzureOpenAI, history: List, system_message:str = None) -> str:
    """Generate next user utterance using Azure OpenAI."""
    
    proxy_system = system_message or (
        "You are a grocery shopper talking on the phone to a customer support agent "
        "Say hello at the beginning of the conversation. You want to buy two Fuji apples and have it delivered "
        "on Wed 23rd at 4pm. Stay in role, never change from grocery shopper. Your questions and responses must "
        "be very short. When you are done say 'goodbye'. "
        "Your address is 21 Baker Street, London but only say it when asked."
    )
    
    # Build conversation context
    prompt = "You are the customer. Respond to the Shop Assistant.\n\n"
    for message in history:
        if message["role"] == "assistant":
            prompt += f"Shop Assistant: {message['content']}\n"
        elif message["role"] == "user":
            prompt += f"You: {message['content']}\n"
    
    prompt += "Respond to the Shop Assistant: "
    
    messages = [
        {"role": "system", "content": proxy_system},
        {"role": "user", "content": prompt}
    ]
    
    response = await client.chat.completions.create(
        model=AZURE_CHAT_DEPLOYMENT_TEXT,
        messages=messages,
        temperature=0.7,
        max_tokens=64,
    )
    
    return response.choices[0].message.content.strip() if response.choices[0].message.content else ""
