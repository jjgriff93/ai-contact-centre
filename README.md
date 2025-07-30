# AI Contact Centre with Voice Live

A basic AI Contact Centre application that uses Azure Communication Services (ACS) to receive phone calls and Azure AI Foundry to provide a voice agent powered by the [Voice Live](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live) API.

## Getting started

### Prerequisites

- An Azure account. If you don't have one, you can create a free account [here](https://azure.microsoft.com/free/).
- [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/)
- [Python 3.12](https://www.python.org/downloads/)
- [Devtunnel CLI](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/overview)
- [UV](https://www.uv.dev/)

### Deploy resources

First authenticate with Azure using the Azure Developer CLI:

```bash
azd auth login
```

Then you can deploy the resources by running the following command:

```bash
azd up
```

This will package up the code in the `api` folder, deploy the Azure resources defined in the `infra` folder, and configure the API to use the Azure Communication Services (ACS) resource created during deployment using a postprovision hook.

### Run API locally

#### First-time setup

- Create a [devtunnel](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/overview):

  ```bash
  task devtunnel:create
  ```

- Host the devtunnel:

  ```bash
  task devtunnel:host
  ```

  Copy the webtunnel URL from the output.

- Update your local azd env file with the devtunnel URL:

  ```bash
  azd env set ACS_CALLBACK_HOST_URI=<your-devtunnel-url>
  ```

  Replace `<your-devtunnel-url>` with the webtunnel URL you copied earlier.

- Run the API:

  ```bash
  task api:run
  ```

- Configure an Event Grid subscription for ACS to send events to your API by following [these instructions](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/incoming-call-notification), selecting Webhook for endpoint type, and supplying your devtunnel URL with the suffix `/api/incomingCall`.
  > Your API needs to be running for the validation handshake to succeed.

#### Each time

> Make sure your devtunnel is running in a terminal window. If not, start it with `task devtunnel:host`.

- Run the API:

  ```bash
  task api:run
  ```

- Call the number you created in ACS to test the API is working. You should hear a greeting and be able to speak to the AI agent.

### Use deployed API

> TODO
