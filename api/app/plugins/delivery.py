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
        return """Availability per day of week:
        - Monday: 12pm - 8pm
        - Tuesday: 1pm - 4pm
        - Wednesday: all slots are taken
        - Thursday: 9am - 5pm
        - Friday: 1pm - 4pm
        - Saturday: 9am - 12pm
        - Sunday: 1pm - 4pm
        """

    @kernel_function
    def book_delivery_slot(self, datetime: str) -> str:
        logger.info(f"@ book_delivery_slot called for {datetime}")
        return "Delivery slot has been booked."
