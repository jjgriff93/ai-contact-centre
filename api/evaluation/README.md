# Conversation Test Runner

The `conversation_test_runner.py` script is designed to simulate and test conversational scenarios with a voice AI system. It uses Azure OpenAI services for text-to-speech (TTS) and speech-to-text (STT) functionalities.

## Pre-requisites

1. AI Foundry - get the endpoint which will look like this: https://<aifoundryname>.cognitiveservices.azure.com
2. In the AI Foundry - deploy base models: 
    gpt-4o-realtime-preview
    gpt-4o-mini-transcribe
    gpt-4o-mini-tts
    gpt-4.1
    
3. **Package manager** Install uv.

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```


## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/jjgriff93/ai-contact-centre.git
cd ai-contact-centre/api
```

### 2. Setup the server

Instruction are here:
[README](https://github.com/jjgriff93/ai-contact-centre/blob/main/README.md)

Install python and the python package dependencies
```bash
cd ./ai-contact-centre/api
uv sync
```

Update the .env file in the ./ai-contact-centre/api folder for the aifoundry endpoint

### 3. Setup the test runner .env file in the api/evaluation directory

We're using token based authentication so you don't need a key, but you will need to az login
```bash
AZURE_OPENAI_ENDPOINT=https://<your-openai-endpoint>.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT=<your-chat-deployment-name>
AZURE_OPENAI_TTS_DEPLOYMENT=<your-tts-deployment-name>
```

### 3. az login  (so the auth works on the openai endpoints)

### 4. Start the server

```bash
cd ./ai-contact-centre/api
uv run fastapi dev
```
### 5. Run the test/conversation code

```bash
cd ~/ai-contact-centre/api
uv run python -m evaluation.conversation_test_runner
```