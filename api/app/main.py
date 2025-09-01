import asyncio
import base64
import json
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from semantic_kernel.connectors.mcp import MCPStreamableHttpPlugin
from semantic_kernel.contents import (AudioContent, ChatHistory,
                                      RealtimeAudioEvent)

from .agents.plugins import CallPlugin, DeliveryPlugin
from .agents.utils import get_agent, handle_realtime_messages
from .config import settings
from .dependencies import get_acs_client
from .routers import calls

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
logger = logging.getLogger(__name__)


@app.get("/")
async def root():
    """Serve the frontend page (used for debugging)."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.websocket("/ws")
async def agent_connect(websocket: WebSocket, acs_client=Depends(get_acs_client)):
    """Websocket endpoint for establishing audio stream with realtime agent."""
    await websocket.accept()
    call_connection_id = websocket.headers.get("x-ms-call-connection-id")

    if not call_connection_id:
        logger.warning("No call connection ID provided in headers indicating direct connection (not ACS). Certain call functions will be mocked.")

    # Determine if running in development mode (for transcription safety)
    is_development_mode = not call_connection_id

    chat_history = ChatHistory()

    # Prepare plugins list
    plugins = [
        CallPlugin(acs_client=acs_client, call_connection_id=call_connection_id),
        DeliveryPlugin()
    ]
    
    # Try to initialize MCP plugin, but fallback gracefully if it fails
    orders_api_plugin = None
    try:
        # Attempt to create MCP plugin with a short timeout
        orders_api_plugin = MCPStreamableHttpPlugin(
            name="Orders API",
            url=settings.MCP_ORDERS_URL,
            load_prompts=False # APIM MCP servers only support tools and this will fail if left enabled
        )
        # Try to connect with timeout
        await asyncio.wait_for(orders_api_plugin.connect(), timeout=5.0)
        plugins.insert(1, orders_api_plugin)  # Insert between CallPlugin and DeliveryPlugin
        logger.info("Successfully connected to MCP Orders API")
    except Exception as e:
        logger.warning(f"Failed to connect to MCP Orders API: {e}. Continuing without orders functionality.")
        orders_api_plugin = None

    # Load realtime agent from template and plugins
    realtime_agent = await get_agent(
        template_name="DeliveryAgent",
        plugins=plugins,
        chat_history=chat_history,
        agent_name="Ollie"
    )

    # Handle the agent connection with proper cleanup
    try:
        # Create the realtime client session
        async with realtime_agent(create_response=True) as client:
            # Start handling the messages from the realtime client with callback to forward the audio to acs
            receive_task = asyncio.create_task(
                handle_realtime_messages(websocket, client, chat_history, is_development_mode)
            )
            # Receive messages from the ACS client and send them to the realtime client
            while True:
                try:
                    # Receive data from the ACS client
                    stream_data = await websocket.receive_text()
                    data = json.loads(stream_data)
                    logger.debug(f"Received data from ACS client: {data}")

                    # If audio send it to the Realtime service
                    if data["kind"] == "AudioData":
                        await client.send(
                            event=RealtimeAudioEvent(
                                audio=AudioContent(
                                    data=data["audioData"]["data"],
                                    data_format="base64",
                                    inner_content=data,
                                ),
                            )
                        )
                except Exception:
                    logger.info("Websocket connection closed.")
                    break

            receive_task.cancel()
    finally:
        # Clean up MCP connection if it was established
        if orders_api_plugin:
            try:
                await orders_api_plugin.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
