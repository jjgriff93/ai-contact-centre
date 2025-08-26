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

### 2. Configure phone number auto-purchase (optional)

You can configure automatic phone number purchasing during deployment by setting azd environment variables:

```bash
# Enable auto-purchase of UK toll-free number
azd env set AZURE_PHONE_NUMBER_AUTO_PURCHASE true
azd env set AZURE_PHONE_NUMBER_COUNTRY GB
azd env set AZURE_PHONE_NUMBER_TYPE toll-free

# Or configure for US toll-free
azd env set AZURE_PHONE_NUMBER_AUTO_PURCHASE true
azd env set AZURE_PHONE_NUMBER_COUNTRY US
azd env set AZURE_PHONE_NUMBER_TYPE toll-free

# Or configure for GB geographic
azd env set AZURE_PHONE_NUMBER_AUTO_PURCHASE true
azd env set AZURE_PHONE_NUMBER_COUNTRY GB
azd env set AZURE_PHONE_NUMBER_TYPE geographic
```

Available configuration options:

- `AZURE_PHONE_NUMBER_AUTO_PURCHASE`: `true` or `false` (default: `false`)
- `AZURE_PHONE_NUMBER_COUNTRY`: Country code - `US`, `CA`, `GB`, `AU`, `FR`, `DE`, `IT`, `ES`, `NL`, `SE`, `NO`, `DK`, `FI`, `IE`, `CH`, `AT`, `BE`, `PT` (default: `GB`)
- `AZURE_PHONE_NUMBER_TYPE`: `toll-free` or `geographic` (default: `toll-free`)

You can view your current azd environment variables with:

```bash
azd env get-values
```

### 3. Deploy resources

Run the following command to deploy the Azure resources defined in the `infra` folder (you'll be prompted to authenticate with Azure):

```bash
task setup:infra
```

This will package up the code in the `api` folder, deploy the Azure resources defined in the `infra` folder, and deploy the packaged `api` to the Azure Container Apps environment.

If auto-purchase is enabled, a phone number will be automatically purchased after deployment. The deployment is idempotent - it will reuse existing numbers that match your configuration and release any that don't match.

### 4. Manage phone numbers

#### Using the CLI tool (recommended)

The project includes a simple CLI for managing phone numbers located in `infra/scripts/`. The CLI automatically uses the same Azure Communication Services resource as your deployed application.

```bash
# Navigate to the API directory (for UV environment)
cd api

# Show available commands
uv run python ../infra/scripts/phone_cli.py --help

# List owned phone numbers
uv run python ../infra/scripts/phone_cli.py list

# Search for available numbers (e.g., UK toll-free)
uv run python ../infra/scripts/phone_cli.py search GB toll-free

# Purchase a phone number (defaults to US toll-free)
uv run python ../infra/scripts/phone_cli.py purchase

# Purchase a specific country/type with auto-confirmation
uv run python ../infra/scripts/phone_cli.py purchase GB toll-free --yes

# Ensure idempotent phone number configuration (used by deployment)
uv run python ../infra/scripts/phone_cli.py ensure GB toll-free --yes

# Release a phone number
uv run python ../infra/scripts/phone_cli.py release +1234567890
```

#### Using Azure portal

You can also purchase a phone number from the Azure portal using the instructions in the [Azure Communication Services documentation](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/telephony/get-phone-number?tabs=windows&pivots=platform-azp-new).

### 5. Run API locally

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

- Configure an Event Grid subscription for ACS to send events to your API by following [these instructions](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/incoming-call-notification), selecting Webhook for endpoint type, and supplying your devtunnel URL with the suffix `/calls/incoming`.
  > Your API needs to be running for the validation handshake to succeed.

#### Each time

- For convenience, you can run the following command to start the devtunnel and API in one go:

  ```bash
  task run
  ```

- Call the number you created in ACS to test the API is working. You should hear a greeting and be able to speak to the AI agent.

### 6. Use Remote API

Like with the local API, set up an Event Grid subscription for the remote API to respond to ACS `IncomingCall`, instead supplying the Container App's URL with the suffix `/calls/incoming`.

> Disable the local API event grid subscription to avoid conflicts.

Then phoning the ACS number should connect you to the AI agent running in the Azure Container App.
