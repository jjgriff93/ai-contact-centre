# Semantic Kernel integration with Azure Live Voice

A quick and simple repo to test the ability to use the existing SK `AzureRealtimeWebsocket` connector - intended for use with Azure OpenAI realtime models directly - with the [Azure Voice Live API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-quickstart?tabs=macos%2Ckeyless), as it implements the same interface (mostly).

Code is based on [Semantic Kernel's Python samples](https://github.com/microsoft/semantic-kernel/blob/main/python/samples/concepts/realtime/README.md).

THis demonstrates it can be used albeit with some limitations I've noticed so far:
- You can't specify a voice model outside of the OpenAI ones in the `AzureRealtimeExecutionSettings` (i.e. to use the Azure nueral voices).
- A websocket url has to be specified in the `AzureRealtimeWebsocket` connector otherwise SK will append `/openai` to the one it creates from the `endpoint` parameter which will result in a websocket 404.

## Instructions
- Deploy an Azure Foundry instance in a supported region for Voice Live (currently `eastus2` or `swedencentral`).
- Create a .env file with the following variable:
  - `AZURE_COGNITIVE_ENDPOINT`: The cognitive services endpoint for your Foundry resource (ends in `.cognitiveservices.azure.com/`).
- Install the required packages:
  ```bash
  uv sync
  ```
- Run the sample:
  ```bash
  uv run
  ```

You'll need to provide microphone permissions. If you're on Mac you may also need to `brew install portaudio` so that `pyaudio` can be installed.
