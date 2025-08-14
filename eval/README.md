# Conversation Test Runner

This eval package is designed to simulate and test conversational scenarios with a voice AI system. It uses Azure OpenAI services for text-to-speech (TTS) and speech-to-text (STT) functionalities.

## Pre-requisites

- Deploy the solution as detailed in the main [README](../../README.md) file.
- Go to your AI Foundry and deploy `gpt-4o-mini-tts` (this is not yet avaiable in `Sweden Central` so manual deployment is required to create a secondary linked region in `eastus2` for this model). Call the deployment `gpt4oMiniTTSDeployment`.

### Run the test/conversation code

First, start the API server and devtunnel in a terminal window:

```bash
task run
```

Then, run the test runner in another terminal window:

```bash
task eval
```

> Make sure you're still logged into Azure either via `azd auth login` or `az login` so that the authentication works on the OpenAI endpoints, otherwise you may see an authentication error.

### 5. Check the test_outputs folder for generated audio and the transcript in json

```bash
cd eval/test_outputs
```
