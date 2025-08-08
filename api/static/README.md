# Debug Frontend

This directory contains the static files for the debug frontend interface.

## Files

- `debug.html` - The main debug interface for testing the AI agent without Azure Communication Services

## Usage

When the FastAPI server is running, access the debug frontend at:

- `http://localhost:8000/debug` (direct route)
- `http://localhost:8000/static/debug.html` (static file route)

## Features

- **WebSocket Connection**: Connect directly to the AI agent without requiring ACS
- **Microphone Input**: Capture audio from your microphone
- **Audio Playback**: Play AI agent responses through your browser
- **Real-time Logging**: See connection status and message logs
- **Volume Control**: Adjust output volume

## Requirements

- Modern web browser with WebRTC support
- Microphone access permissions
- Azure AI Services endpoint configured (for the AI agent to work)

## Limitations

- Audio format conversion between browser (WebM/Opus) and AI service (PCM) is simplified
- This is intended for debugging and development, not production use
- Some call automation functions available in the full ACS integration are not available in debug mode