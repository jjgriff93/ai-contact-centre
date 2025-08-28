import logging
from typing import Annotated, Optional

from azure.communication.callautomation.aio import CallAutomationClient
from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CallPlugin:
    """Call plugin for managing the voice call."""

    def __init__(self, acs_client: CallAutomationClient, call_connection_id: Optional[str]):
        self._acs_client = acs_client
        self._call_connection_id = call_connection_id

    @kernel_function
    async def get_caller_phone_number(self) -> str:
        """Retrieves the caller's phone number."""
        logger.info("@ get_caller_phone_number has been called")

        if not self._call_connection_id:
            logger.warning("No call connection ID available to get caller phone number. Returning test number")
            return "888888888888"

        # Retrieve the caller's phone number from the ACS client
        caller_info = await self._acs_client.get_call_connection(self._call_connection_id).get_call_properties()
        # TODO: get caller number
        return "888888888888"

    @kernel_function
    def transfer_to_human(
        self,
        call_summary: Annotated[str, "A brief summary of the interaction with the customer for the human agent to review."]
    ):
        """Transfer the call to a human colleague."""
        logger.info(f"@ transfer_to_human called with summary: {call_summary}")

    @kernel_function
    async def hangup(self):
        """Ends the ACS call connection."""
        logger.info("@ hangup has been called")

        if not self._call_connection_id:
            logger.warning("No call connection ID available to hang up the call.")
        else:
            # Hang up the call for everyone in the call
            await self._acs_client.get_call_connection(self._call_connection_id).hang_up(
                is_for_everyone=True
            )
            logger.info("Call has been hung up.")