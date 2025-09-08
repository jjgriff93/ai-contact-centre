import json
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from azure.identity.aio import (DefaultAzureCredential,
                                get_bearer_token_provider)
from fastapi import WebSocket
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import AzureRealtimeWebsocket
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_realtime_execution_settings import \
    AzureRealtimeExecutionSettings
from semantic_kernel.connectors.mcp import MCPStreamableHttpPlugin
from semantic_kernel.contents import (ChatHistory, FunctionCallContent,
                                      FunctionResultContent)
from semantic_kernel.functions import KernelArguments
from semantic_kernel.prompt_template import (KernelPromptTemplate,
                                             PromptTemplateConfig)

from ..config import settings
from .azure_voice_live import (AzureVoiceLiveExecutionSettings,
                               AzureVoiceLiveWebsocket,
                               PatchedAzureRealtimeWebsocket)

logger = logging.getLogger(__name__)


def export_chat_history(chat_history: ChatHistory, from_index: int = 0) -> list[dict[str, Any]]:
    """Convert chat history to a list of dicts suitable for JSON serialization."""
    messages_raw = chat_history.messages[from_index:]

    messages_formatted: list[dict[str, Any]] = []
    for msg in messages_raw:
        message_data: dict[str, Any] = {"role": msg.role.value}
        if msg.content:
            message_data["content"] = str(msg.content)

        function_calls: list[dict[str, Any]] = []
        for item in msg.items:
            if isinstance(item, FunctionCallContent):
                parsed_args: dict | list | str | None
                if isinstance(item.arguments, str):
                    try:
                        parsed_args = json.loads(item.arguments)
                    except Exception:
                        parsed_args = item.arguments
                elif isinstance(item.arguments, dict):
                    parsed_args = item.arguments
                else:
                    parsed_args = None

                function_calls.append(
                    {
                        "function_name": item.function_name,
                        "plugin": item.plugin_name,
                        "arguments": parsed_args,
                    }
                )
            elif isinstance(item, FunctionResultContent):
                function_calls.append(
                    {
                        "function_name": item.function_name,
                        "plugin": item.plugin_name,
                        "arguments_sent": item.metadata["arguments"],
                        "arguments_used": item.metadata["used_arguments"],
                        "result": item.result,
                    }
                )

        if function_calls:
            message_data["function_calls"] = function_calls

        messages_formatted.append(message_data)

    return messages_formatted


async def get_agent(template_name: str, plugins: list[object], chat_history: ChatHistory, **kwargs) -> AzureRealtimeWebsocket:
    """
    Get a realtime voice agent by rendering a prompt template and adding plugins.

    Args:
        template_name: The name of the prompt template to use for the agent (in the prompts directory).
        plugins: A list of plugins to add to the agent.
        chat_history: The chat history object to use for the agent.
        **kwargs: Additional keyword arguments to pass to the prompt template rendering.
    """
    yaml_path = Path(__file__).parent / "prompts" / f"{template_name}.yaml"
    with open(yaml_path, "r") as file:
        yaml_content = file.read()
        yaml_data = yaml.safe_load(yaml_content)
    
    prompt_template_config = PromptTemplateConfig(**yaml_data)
    prompt_template = KernelPromptTemplate(prompt_template_config=prompt_template_config)
    prompt_arguments = KernelArguments(**kwargs)

    rendered_prompt = await prompt_template.render(Kernel(), prompt_arguments)
    logger.debug(f"Rendered prompt: {rendered_prompt}")

    # Load voice live execution settings from a single YAML file (env override supported)
    config_path = str(Path(__file__).parent / "settings" / settings.REALTIME_CONFIG_PATH)
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    # Determine service mode from config
    service = cfg.pop("service", None).lower()
    deployment_name = cfg.pop("deployment_name", None) or "gpt-4o-realtime-preview"
    api_version = cfg.pop("api_version", None)

    # Prepare execution settings payload
    exec_payload = dict(cfg)

    # Merge rendered instructions, taking precedence over YAML if provided via template
    # YAML may include an instructions placeholder; always override with rendered prompt when present
    exec_payload["instructions"] = rendered_prompt

    # Construct pydantic settings allowing nested dicts to be parsed into models
    if service == "azure_realtime":
        execution_settings = AzureRealtimeExecutionSettings(
            function_choice_behavior=FunctionChoiceBehavior.Auto(),
            **exec_payload,
        )
        # Use patched base to sanitise non-string function results for realtime
        client_class = PatchedAzureRealtimeWebsocket
    elif service == "azure_voice_live":
        execution_settings = AzureVoiceLiveExecutionSettings(
            function_choice_behavior=FunctionChoiceBehavior.Auto(),
            **exec_payload,
        )
        client_class = AzureVoiceLiveWebsocket
    else:
        raise ValueError(f"Unknown service: {service}")

    chat_history.add_system_message(execution_settings.instructions)

    return client_class(
        endpoint=settings.AZURE_AI_SERVICES_ENDPOINT,
        deployment_name=deployment_name,
        ad_token_provider=get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        ),
        api_version=api_version,
        plugins=plugins,
        settings=execution_settings,
    )

def _expand_env_vars_in_obj(obj: Any) -> Any:
    """Recursively expand ${VAR} environment variable references in strings within a nested object."""
    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars_in_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars_in_obj(v) for v in obj]
    return obj

async def load_mcp_plugins_from_folder(folder: str | Path | None = None) -> list[MCPStreamableHttpPlugin]:
    """Load MCP servers from YAML files and return a list of MCPStreamableHttpPlugin instances.

    The YAML schema per file:
      - name: string (required)
      - url: string (required, supports ${ENV_VAR})
      - headers: object of string->string (optional, supports ${ENV_VAR})
      - load_prompts: bool (optional, default False)
      - enabled: bool (optional, default True)
    """
    folder_path = Path(folder) if folder else Path(__file__).parent / "mcp"
    plugins: list[MCPStreamableHttpPlugin] = []
    if not folder_path.exists():
        return plugins

    for file in sorted(folder_path.glob("*.y*ml")):
        try:
            with open(file, "r") as f:
                raw = yaml.safe_load(f) or {}
            cfg = _expand_env_vars_in_obj(raw)
            if not cfg or cfg.get("enabled", True) is False:
                continue
            name = cfg.get("name")
            url = cfg.get("url")
            if not name or not url:
                logger.warning(f"Skipping MCP config {file.name}: missing name or url")
                continue
            headers = cfg.get("headers") or None
            load_prompts = bool(cfg.get("load_prompts", False))
            plugin = MCPStreamableHttpPlugin(
                name=name,
                url=url,
                headers=headers,
                load_prompts=load_prompts,
            )
            plugins.append(plugin)
        except Exception as e:
            logger.error(f"Failed to load MCP plugin from {file}: {e}")
    return plugins

def get_attr(obj: Any, path: str, default: Any | None = None) -> Any | None:
    """Safely get a nested attribute by dot path (returns default on any miss)."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return default
        cur = getattr(cur, part, None)
    return cur if cur is not None else default


async def send_chat_history(websocket: WebSocket, chat_history: ChatHistory, from_index: int) -> int:
    """Send chat history delta to the client and return new index marker."""
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "kind": "ChatHistory",
                    "data": export_chat_history(chat_history, from_index=from_index),
                }
            )
        )
    except Exception:
        logger.exception("Failed to send ChatHistory to websocket")
    return len(chat_history.messages)


# NOTE: handle_realtime_messages moved to realtime.py to keep this file focused on utilities.
