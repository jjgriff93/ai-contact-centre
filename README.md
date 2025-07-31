# AI Contact Centre with Voice Live

A basic AI Contact Centre application that uses Azure Communication Services (ACS) to receive phone calls and Azure AI Foundry to provide a voice agent powered by the [Voice Live](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live) API.

## Getting started

### 1. Prerequisites

- An Azure account. If you don't have one, you can create a free account [here](https://azure.microsoft.com/free/).
- [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/)
- [Python 3.12](https://www.python.org/downloads/)
- [Devtunnel CLI](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/overview)
- [UV](https://www.uv.dev/)
- [Taskfile](https://taskfile.dev/)

### 2. Deploy resources

Run the following command to deploy the Azure resources defined in the `infra` folder (you'll be prompted to authenticate with Azure):

```bash
task setup:infra
```

This will package up the code in the `api` folder, deploy the Azure resources defined in the `infra` folder, and deploy the packaged `api` to the Azure Container Apps environment.

### 3. Purchase an ACS phone number

You can purchase a phone number from the Azure portal or using the Azure CLI. Follow the instructions in the [Azure Communication Services documentation](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/telephony/get-phone-number?tabs=windows&pivots=platform-azp-new) to purchase a phone number.

### 4. Run API locally

#### First-time setup

- Create a [devtunnel](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/overview):

  ```bash
  task setup:devtunnel
  ```

- Host the devtunnel:

  ```bash
  task run:devtunnel
  ```

  Copy the webtunnel URL from the output.

- Update your local azd env file with the devtunnel URL:

  ```bash
  azd env set AZURE_ACS_CALLBACK_HOST_URI <your-devtunnel-url>
  ```

  Replace `<your-devtunnel-url>` with the webtunnel URL you copied earlier.

- Run the API:

  ```bash
  task run:api
  ```

- Configure an Event Grid subscription for ACS to send events to your API by following [these instructions](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/incoming-call-notification), selecting Webhook for endpoint type, and supplying your devtunnel URL with the suffix `/api/incomingCall`.
  > Your API needs to be running for the validation handshake to succeed.

#### Each time

- For convenience, you can run the following command to start the devtunnel and API in one go:

  ```bash
  task run
  ```

- Call the number you created in ACS to test the API is working. You should hear a greeting and be able to speak to the AI agent.

### 5. Use Remote API

Like with the local API, set up an Event Grid subscription for the remote API to respond to ACS `IncomingCall`, instead supplying the Container App's URL with the suffix `/api/incomingCall`.

> Disable the local API event grid subscription to avoid conflicts.

Then phoning the ACS number should connect you to the AI agent running in the Azure Container App.
