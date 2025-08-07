import logging
from datetime import date, timedelta

import numpy as np
from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeliveryPlugin:
    """Delivery plugin for managing delivery-related tasks."""
    def __init__(self):
        self.current_verified_order_number = None
    
    @kernel_function
    def verify_identity(self, order_number: int, delivery_postcode: str, order_phone_number: int | None = None) -> str:
        """Verify the customer's identity. This MUST be performed before any delivery actions can be performed."""
        logger.info(f"@ verify_identity called for order {order_number}, postcode {delivery_postcode}, phone {order_phone_number}")
        # TODO: retrieve order by order number
        # TODO: verify delivery postcode matches order postcode
        # TODO: get phone number from current ACS context and verify it matches order phone number
        self.current_verified_order_number = order_number
        return f"Customer has been verified against order {order_number}. Delivery actions against this order can now be performed."

    @kernel_function
    def schedule_delivery(self, slot_id: str) -> str:
        """Schedule a delivery for the customer.
        Args:
            slot_id (str): The ID of the delivery slot to schedule. Slot IDs can be retrieved using the get_available_slots_for_delivery function.
    
        Returns:
            str: A message indicating the delivery has been scheduled or if there was an issue.
        """
        logger.info(f"@ schedule_delivery called for id {slot_id}")

        if not self.current_verified_order_number:
            logger.warning("Attempted to schedule delivery without verifying identity.")
            raise ValueError("Please verify customer's identity before scheduling a delivery.")

        return f"Delivery has been scheduled for slot {slot_id}."

    @kernel_function
    def get_available_slots_for_delivery(self, start_date: str = "", end_date: str = "") -> dict[str, str]:
        """Get the slots that are available for delivery for the current verified order.

        IMPORTANT: This function should only be called after the customer's identity has been verified and will raise an error if called otherwise.

        Args:
            start_date (str): The start date (in ISO format) for the delivery slots query. If empty, defaults to today.
            end_date (str): The end date (in ISO format) for the delivery slots query. If empty, defaults to 7 days from start date.

        Returns:
            dict[str, str]: A dictionary indicating the availability of delivery slots for the specified date range.
        """
        logger.info(f"@ get_available_slots_for_delivery called for {start_date} to {end_date}")

        if not self.current_verified_order_number:
            logger.warning("Attempted to get available slots without verifying identity.")
            raise ValueError("Please verify customer's identity before getting available delivery slots.")

        if not start_date:
            start_date = date.today().isoformat()
        if not end_date:
            end_date = (date.today() + timedelta(days=7)).isoformat()

        # Mock implementation for available slots
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        range_days = (end - start).days
        randays = np.random.choice(range_days, 3, replace=False)
        # Example: return {"001": "2023-10-01T10:00:00Z", "002": "2023-10-02T10:00:00Z", "003": "2023-10-03T10:00:00Z"}
        return {str(i+1).zfill(3): (start + timedelta(days=int(d))).isoformat() + "T10:00:00Z" for i, d in enumerate(randays)}
