# Conversation Test Runner

The `conversation_test_runner.py` script is designed to simulate and test conversational scenarios with a voice AI system. It uses Azure OpenAI services for text-to-speech (TTS) and speech-to-text (STT) functionalities.

## Pre-requisites

- Deploy the solution as detailed in the main [README](../../README.md) file.
- Go to your AI Foundry and deploy `gpt-4o-mini-tts` (this is not yet avaiable in `Sweden Central` so manual deployment is required to create a secondary linked region in `eastus2` for this model). Call the deployment `gpt4oMiniTTSDeployment`.

### Run the test/conversation code

First, ensure you're logged into Azure either via `azd auth login` or `az login` so that the authentication works on the OpenAI endpoints.

Then, start the API server in a terminal window:

```bash
task api
```

Finally, run the test runner in another terminal window:

```bash
task test
```

### 5. Check the test_outputs folder for generated audio and the transcript in json

```bash
cd api/test_outputs
```
