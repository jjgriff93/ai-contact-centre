import logging

from azure.communication.callautomation.aio import CallAutomationClient
from semantic_kernel.functions import kernel_function


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CallPlugin:
    """Call plugin for managing the ACS connection."""

    def __init__(self, acs_client: CallAutomationClient, call_connection_id: str):
        self._acs_client = acs_client
        self._call_connection_id = call_connection_id

    @kernel_function
    async def hangup(self):
        """When the user is done, say goodbye and then call this function."""
        logger.info("@ hangup has been called!")
        await self._acs_client.get_call_connection(self._call_connection_id).hang_up(
            is_for_everyone=True
        )
