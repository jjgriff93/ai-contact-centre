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

    chat_history = ChatHistory()

    # Initialise MCP plugin with async context manager
    async with MCPStreamableHttpPlugin(
        name="Orders API",
        url=settings.MCP_ORDERS_URL,
        load_prompts=False # APIM MCP servers only support tools and this will fail if left enabled
    ) as orders_api_plugin:

        # Load realtime agent from template and plugins
        realtime_agent = await get_agent(
            template_name="DeliveryAgent",
            plugins=[
                CallPlugin(acs_client=acs_client, call_connection_id=call_connection_id),
                orders_api_plugin,
                DeliveryPlugin()
            ],
            chat_history=chat_history,
            agent_name="Ollie"
        )

        # Create the realtime client session
        async with realtime_agent(create_response=True) as client:
            # Start handling the messages from the realtime client with callback to forward the audio to acs
            receive_task = asyncio.create_task(
                handle_realtime_messages(websocket, client, chat_history)
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
