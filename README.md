# AI Contact Centre with Voice Live

A basic AI Contact Centre application that uses Azure Communication Services (ACS) to receive phone calls and Azure AI Foundry to provide a voice agent powered by the [Voice Live](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live) API.

## Run locally

- Deploy the following resources in Azure:

  - [Azure Communication Services](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/voice-quickstart-portal)
  - [Azure AI Foundry Project](https://learn.microsoft.com/en-us/azure/ai-foundry/quickstart)

- Create a new phone number in Azure Communication Services (ACS)

- Install the required packages:

  ```bash
  uv sync
  ```

- Authenticate with Azure CLI:

  ```bash
  az login
  ```

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

- Run the API:

  ```bash
  cd api && uv run fastapi dev
  ```

- Configure an Event Grid subscription for ACS to send events to your API by following [these instructions](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/incoming-call-notification), selecting Webhook for endpoint type, and supplying your devtunnel URL with the suffix `/api/incomingCall`.
  > Your API needs to be running for the validation handshake to succeed.

- Call the number you created in ACS to test the API is working. You should hear a greeting and be able to speak to the AI agent.

## Deployment

TODO: deploy with `azd provision` and [UV](https://docs.astral.sh/uv/guides/integration/fastapi/#deployment)
