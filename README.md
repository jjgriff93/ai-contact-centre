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

### Interact with the AI Contact Centre agent

To interact with the AI Contact Centre agent, you will need to call the phone number created in ACS during the deployment process. You can find this number in the Azure portal under the Communication Services resource created by `azd up`.

When you call this number, you should hear a greeting and be able to speak to the AI agent powered by Voice Live.

### Run API locally

To run the API locally, follow these steps:

- Start a [devtunnel](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/overview):

  ```bash
  devtunnel login
  devtunnel create --allow-anonymous
  devtunnel port create -p 8000
  devtunnel host
  ```

  Note your webtunnel URL provided by the devtunnel command.

- In a new shell in the `api/app` folder, copy the `.env.example` file to `.env` and fill in the required values:

  ```bash
  cp .env.example .env
  ```

  > TODO: Generate this automatically using azd outputs

- Run the API:

  ```bash
  uv run fastapi dev
  ```

- Configure an Event Grid subscription for ACS to send events to your API by following [these instructions](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/incoming-call-notification), selecting Webhook for endpoint type, and supplying your devtunnel URL with the suffix `/api/incomingCall`.
  > Your API needs to be running for the validation handshake to succeed.

- Call the number you created in ACS to test the API is working. You should hear a greeting and be able to speak to the AI agent.
