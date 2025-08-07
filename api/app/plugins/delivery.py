import logging

from semantic_kernel.functions import kernel_function


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeliveryPlugin:
    """Delivery plugin for managing delivery-related tasks."""

    @kernel_function
    def get_available_slots_for_delivery(self, date: str) -> str:
        """Get the slots that are available for delivery.

        Args:
            date (str): The date for which to get available delivery slots.

        Returns:
            str: A message indicating the availability of delivery slots.
        """
        logger.info(f"@ get_available_slots_for_delivery called for {date}")
        return "All slots are taken for Wednesday, all other days are free to take."
