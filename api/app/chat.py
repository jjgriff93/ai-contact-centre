"""
Text-based Chat API for Delivery Agent

This module provides a text-based chat interface as an alternative to the WebSocket-based
voice chat. It uses the same Semantic Kernel agent and plugins as the voice interface
but operates with text messages instead of audio.

Endpoints:
- GET  /           - Serve the chat interface HTML page
- POST /chat       - Send a chat message and get response
- GET  /chat/conversations - List all active conversations

Usage:
1. Open browser to http://localhost:8010/ for the chat interface
2. Or make HTTP POST requests to /chat with JSON: {"message": "Hello", "conversation_id": "optional"}

The chat endpoint uses the same DeliveryAgent template and plugins (CallPlugin, DeliveryPlugin)
as the voice interface, providing the same functionality for delivery scheduling.

Conversations are managed by the ConversationManager class that stores all agents/chat histories in memory.
"""

import httpx
import logging
import os
import yaml
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncAzureOpenAI
from pydantic import BaseModel
from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import KernelPromptTemplate, PromptTemplateConfig
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

from .agents.plugins import CallPlugin, DeliveryPlugin
from .routers import calls

from .config import settings


app = FastAPI()

# Mount static files and add routers
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")
app.include_router(calls.router)

# Configure root logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger().setLevel(LOG_LEVEL)
logging.getLogger("kernel").setLevel(LOG_LEVEL)
logger = logging.getLogger(__name__)


# Request/Response models
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str

# Conversation Manager
class Conversation(BaseModel):
    """Represents a single conversation with its state and components."""
    conversation_id: str
    chat_agent: object = None
    thread: object = None

class ConversationManager:
    """Manages all active conversations with thread-safe operations."""

    def __init__(self):
        self._conversations: dict[str, Conversation] = {}
        self._conversation_counter = 0

    def create_conversation_id(self) -> str:
        """Generate a new unique conversation ID."""
        self._conversation_counter += 1
        return f"chat_{self._conversation_counter}"

    def add_conversation(self, conversation: Conversation) -> None:
        """Add a new conversation to the manager."""
        self._conversations[conversation.conversation_id] = conversation
        logger.info(f"Created new conversation: {conversation.conversation_id}")

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Get a conversation by ID, returns None if not found."""
        return self._conversations.get(conversation_id)

    def list_conversation_ids(self) -> list[str]:
        """Get a list of all active conversation IDs."""
        return list(self._conversations.keys())


async def setup_chat_agent(template_name: str, config_file: str, **kwargs):
    """ Get a text-based chat agent using Azure OpenAI."""

    # Load and render the prompt template
    yaml_path = Path(__file__).parent / "agents" / "prompts" / f"{template_name}.yaml"
    with open(yaml_path, "r") as file:
        yaml_data = yaml.safe_load(file.read())

    prompt_template_config = PromptTemplateConfig(**yaml_data)
    prompt_template = KernelPromptTemplate(prompt_template_config=prompt_template_config)
    prompt_arguments = KernelArguments(**kwargs)
    system_prompt = await prompt_template.render(Kernel(), prompt_arguments)

    # Load execution settings from YAML file
    config_path = str(Path(__file__).parent / "agents" / "settings" / config_file)
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    deployment_name = cfg.pop("deployment_name", None)
    api_version = cfg.pop("api_version", None)
    execution_settings = dict(cfg)

    # Create Azure OpenAI chat completion service
    token_provider=get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    client = AsyncAzureOpenAI(
        azure_endpoint=settings.AZURE_AI_SERVICES_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version="2024-08-01-preview",
        http_client=httpx.AsyncClient(verify=False, timeout=httpx.Timeout(60.0))
    )

    chat_completion_service = AzureChatCompletion(
        deployment_name=deployment_name,
        endpoint=settings.AZURE_AI_SERVICES_ENDPOINT,
        api_version=api_version,
        ad_token_provider=token_provider,
        async_client=client
    )

    # Create Chat Agent
    chat_agent = ChatCompletionAgent(
        service=chat_completion_service,
        name="chat_agent",
        instructions=system_prompt,
        plugins=[
            CallPlugin(acs_client=None, call_connection_id=None),
            DeliveryPlugin(),
        ],
        arguments=KernelArguments(settings=execution_settings)
    )

    return chat_agent


# Global conversation manager instance
conversation_manager = ConversationManager()


@app.get("/")
async def root():
    """Serve the chat interface page."""
    return FileResponse(Path(__file__).parent / "static" / "chat.html")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Text-based chat endpoint using a ChatCompletionAgent"""
    try:
        conversation_id = request.conversation_id or conversation_manager.create_conversation_id()

        # Get or create conversation
        conversation = conversation_manager.get_conversation(conversation_id)
        if conversation is None:
            chat_agent = await setup_chat_agent(template_name="DeliveryAgent", config_file="chat.yaml", agent_name="Sam")
            conversation = Conversation(
                conversation_id=conversation_id,
                chat_agent=chat_agent,
            )
            conversation_manager.add_conversation(conversation)

        # Generate next message in conversation based on input
        response = await conversation.chat_agent.get_response(messages=request.message, thread=conversation.thread)
        
        # Store the updated conversation thread
        conversation.thread = response.thread

        return ChatResponse(
            response=response.message.content,
            conversation_id=conversation_id
        )

    except Exception as e:
        logger.exception(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/chat/conversations")
async def list_conversations():
    """List all active conversations with metadata"""
    conversations = []
    for conv_id in conversation_manager.list_conversation_ids():
        summary = conversation_manager.get_conversation_summary(conv_id)
        if summary:
            conversations.append(summary)
    
    return {
        "conversations": conversations,
        "stats": conversation_manager.get_stats()
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
