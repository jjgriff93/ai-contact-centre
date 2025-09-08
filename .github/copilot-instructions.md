# AI Contact Centre with Voice Live

AI Contact Centre is a Python 3.12 FastAPI application that uses Azure Communication Services (ACS) to handle phone calls and Azure AI Foundry to provide voice agents powered by the Voice Live API. The application includes conversation evaluation framework and Azure infrastructure deployment.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Prerequisites Installation
Install these tools before working with the repository:

- **Python 3.12**: Must be available as `python3` or `python`
- **UV Package Manager**: `pip install uv` (fast Python package manager)
- **Taskfile**: Download from https://taskfile.dev/installation/ or use:
  ```bash
  sh -c "$(curl --location https://raw.githubusercontent.com/go-task/task/main/install-task.sh)" -- -d -b ~/.local/bin
  export PATH="$HOME/.local/bin:$PATH"
  ```
- **Azure Developer CLI (azd)**: Download from https://aka.ms/install-azd.sh for Azure deployment
- **DevTunnel CLI**: Download from https://aka.ms/install-dev-tunnels for local development tunneling
- **Docker**: For containerized deployment

### Build and Setup Process
Bootstrap and build the repository with these commands:

1. **Install dependencies** (FAST - takes 5-10 seconds):
   ```bash
   cd api && uv sync
   ```

2. **Validate FastAPI installation**:
   ```bash
   cd api && uv run fastapi dev --help
   ```

3. **Test API startup** (will fail on missing Azure credentials - this is expected):
   ```bash
   cd api && uv run fastapi dev app/main.py
   # Should fail with: "AZURE_ACS_ENDPOINT Field required" and "AZURE_AI_SERVICES_ENDPOINT Field required"
   ```

4. **Use Taskfile for automation**:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   task --list-all  # Shows: run:api, run:devtunnel, setup:infra, setup:devtunnel, test, run
   ```

### Docker Build Process
- **Build container**: `docker build -t aicc-api .` -- takes 2-5 minutes. NEVER CANCEL. Set timeout to 10+ minutes.
- **NOTE**: Docker build may fail in restricted network environments due to SSL certificate issues when downloading Python packages.

## Azure Infrastructure and Environment

### Deploy Azure Resources
- **Deploy infrastructure**: `task setup:infra` -- executes `azd auth login` then `azd up`. Takes 5-15 minutes. NEVER CANCEL. Set timeout to 20+ minutes.
- **Purchase ACS phone number**: Must be done manually via Azure portal following Microsoft documentation
- **Configure Event Grid**: Must be done manually to connect ACS events to the API webhook endpoint

### Local Development with Azure
- **Setup development tunnel**: `task setup:devtunnel` -- creates tunnel for local development
- **Run tunnel**: `task run:devtunnel` -- hosts the tunnel for Azure callbacks
- **Set callback URI**: `azd env set AZURE_ACS_CALLBACK_HOST_URI <your-devtunnel-url>`
- **Run API locally**: `task run:api` -- starts FastAPI development server
- **Run both together**: `task run` -- starts tunnel and API simultaneously

## Testing and Validation

### Evaluation Framework
- **Run conversation tests**: `task test` -- executes `uv run python -m evaluation.conversation_test_runner`. Takes 2-5 minutes. NEVER CANCEL. Set timeout to 10+ minutes.
- **Prerequisites for testing**: 
  - Azure credentials configured (`azd auth login` or `az login`)
  - Deploy `gpt-4o-mini-tts` model in AI Foundry (call it `gpt4oMiniTTSDeployment`)
  - API server must be running for webhook validation
- **Test outputs**: Check `api/test_outputs/` for generated audio files and transcripts

### Validation Scenarios
Always run these validation steps after making changes:

1. **Basic Build Validation**:
   ```bash
   cd api && uv sync && uv run fastapi dev --help
   ```

2. **Code Syntax Validation** - verify imports work:
   ```bash
   cd api && uv run python -c "import app.plugins.call, app.plugins.delivery; print('Plugins import successfully')"
   ```

3. **API Startup Test** (should fail gracefully without Azure credentials):
   ```bash
   cd api && timeout 10 uv run fastapi dev app/main.py
   # Expected: ValidationError for missing AZURE_ACS_ENDPOINT and AZURE_AI_SERVICES_ENDPOINT
   ```

4. **Azure-dependent Testing** (requires Azure credentials):
   ```bash
   task run  # Start API and tunnel
   task test # Run conversation evaluation tests
   ```

5. **End-to-End Call Testing**: Phone the ACS number and verify the AI agent responds appropriately

## Timing Expectations and Critical Warnings

### NEVER CANCEL - Build and Test Times
- **UV dependency sync**: 5-10 seconds
- **API startup**: 5 seconds (fails on credentials - expected)
- **Docker build**: 2-5 minutes. **NEVER CANCEL** - set timeout to 10+ minutes
- **Azure infrastructure deployment**: 5-15 minutes. **NEVER CANCEL** - set timeout to 20+ minutes  
- **Conversation evaluation tests**: 2-5 minutes. **NEVER CANCEL** - set timeout to 10+ minutes

### Required Environment Variables
The API requires these Azure endpoints to run:
- `AZURE_ACS_ENDPOINT`: Azure Communication Services endpoint URL
- `AZURE_AI_SERVICES_ENDPOINT`: Azure AI Foundry/Cognitive Services endpoint URL
- `AZURE_ACS_CALLBACK_HOST_URI`: Webhook callback URL (for local dev, use devtunnel URL)

## Common Tasks and File Structure

### Key Directories
```
api/                    # Main Python application
├── app/               # FastAPI application code
│   ├── main.py       # Main API server (340 lines)
│   ├── plugins/      # Call and delivery management plugins
│   └── azure_voice_live.py # Azure Voice Live integration
├── evaluation/       # Conversation testing framework
└── pyproject.toml   # Python dependencies managed by UV

infra/                 # Azure Bicep infrastructure templates
Taskfile.yml          # Task automation definitions
azure.yaml            # Azure deployment configuration
```

### Application Architecture
- **API Server**: FastAPI app with WebSocket endpoints for voice streaming
- **Voice Integration**: Azure Voice Live API for real-time voice processing  
- **Call Management**: Azure Communication Services for phone call handling
- **AI Plugins**: Semantic Kernel plugins for call and delivery management
- **Evaluation**: Automated conversation testing with Azure AI services

### Development Workflow
1. Make code changes to API or evaluation framework
2. Run build validation: `cd api && uv sync`
3. Test API startup: `cd api && timeout 10 uv run fastapi dev app/main.py`
4. For Azure-dependent testing: Start `task run`, then `task test`
5. For infrastructure changes: `task setup:infra`

### Error Troubleshooting
- **Missing Azure credentials**: Expected for local development without proper Azure setup
- **SSL certificate errors in Docker**: Indicates restricted network environment
- **DevTunnel/AZD command not found**: Tools need to be installed per prerequisites
- **Validation errors on API startup**: Verify environment variables are set correctly

## Notes for AI Coding Agents
- Always validate that API can import successfully before extensive code changes
- The application cannot function without Azure credentials, but build/syntax validation works without them
- Use UV instead of pip for all Python package management - it's significantly faster
- The evaluation framework requires a running API server for proper webhook testing
- Docker builds work in normal environments but may fail in restricted networks