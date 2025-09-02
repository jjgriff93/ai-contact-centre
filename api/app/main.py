import asyncio
import base64
import json
import logging
import os
from contextlib import AsyncExitStack
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from semantic_kernel.contents import (AudioContent, ChatHistory,
                                      RealtimeAudioEvent)

from .agents.plugins import CallPlugin, DeliveryPlugin
from .agents.utils import (get_agent, handle_realtime_messages,
                           load_mcp_plugins_from_folder)
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
logging.getLogger("kernel").setLevel(LOG_LEVEL)
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

    # Load MCP plugins from YAML files and enter their async contexts
    mcp_plugins = await load_mcp_plugins_from_folder()
    async with AsyncExitStack() as stack:
        bound_mcp_plugins = []
        for p in mcp_plugins:
            try:
                bound_mcp_plugins.append(await stack.enter_async_context(p))
            except Exception:
                # Notify client and close with an internal error code if MCP connect fails
                err_message = {
                    "kind": "Error",
                    "code": "MCPPluginConnectionError",
                    "message": "Failed to connect to an MCP server. Check server availability and configuration.",
                }
                try:
                    await websocket.send_text(json.dumps(err_message))
                except Exception:
                    pass
                logger.exception("MCP plugin connection failed while establishing websocket")
                await websocket.close(code=1011)
                return

        # Load realtime agent from template and plugins
        realtime_agent = await get_agent(
            template_name="DeliveryAgent",
            plugins=[
                *bound_mcp_plugins,
                CallPlugin(acs_client=acs_client, call_connection_id=call_connection_id),
                DeliveryPlugin()
            ],
            chat_history=chat_history,
            agent_name="Sam"
        )

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
                except Exception as e:
                    logging.error(f"Error occurred while processing websocket message: {e}")
                    break

            receive_task.cancel()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
