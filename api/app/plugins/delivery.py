import logging
from datetime import date, datetime, timedelta

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
            start_date (str): Optional start date (ISO-8601, e.g. YYYY-MM-DD or full datetime). Defaults to today when omitted/empty.
            end_date (str): Optional end date (ISO-8601). Defaults to 7 days after the start date when omitted/empty.

        Returns:
            dict[str, str]: Mapping of slot_id to slot start time in UTC ISO-8601 (Z) within the requested date window.
        """
        logger.info(f"@ get_available_slots_for_delivery called for {start_date} to {end_date}")

        if not self.current_verified_order_number:
            logger.warning("Attempted to get available slots without verifying identity.")
            raise ValueError("Please verify customer's identity before getting available delivery slots.")

        # Resolve start and end dates
        def parse_iso_to_date(value: str) -> date:
            if not value:
                raise ValueError("Empty date value cannot be parsed.")
            # Support full datetime or date-only strings
            try:
                # Try date-only first
                return date.fromisoformat(value.split("T")[0])
            except Exception as parse_error:
                raise ValueError(f"Invalid date format: {value}") from parse_error

        if start_date:
            start_date_value: date = parse_iso_to_date(start_date)
        else:
            start_date_value = date.today()

        if end_date:
            end_date_value: date = parse_iso_to_date(end_date)
        else:
            end_date_value = start_date_value + timedelta(days=7)

        if end_date_value < start_date_value:
            raise ValueError("end_date must be on or after start_date")

        # Generate randomized mock slots within the window (inclusive)
        rng = np.random.default_rng()
        possible_hours = [8, 10, 12, 14, 16, 18]
        slots: dict[str, str] = {}

        current_day = start_date_value
        # Safety cap to avoid excessive generation
        max_days = 31
        days_generated = 0
        while current_day <= end_date_value and days_generated < max_days:
            # Between 1 and len(possible_hours) slots per day
            slots_for_day = int(rng.integers(1, len(possible_hours) + 1))
            selected_hours = list(rng.choice(possible_hours, size=slots_for_day, replace=False))
            selected_hours.sort()

            for hour in selected_hours:
                slot_dt = datetime(
                    year=current_day.year,
                    month=current_day.month,
                    day=current_day.day,
                    hour=int(hour),
                    minute=0,
                    second=0,
                )
                # Construct a readable stable slot id
                slot_id = f"SLOT-{current_day.strftime('%Y%m%d')}-{hour:02d}00"
                # Represent time as UTC with Z suffix for simplicity
                slot_iso_utc = slot_dt.isoformat(timespec="seconds") + "Z"
                slots[slot_id] = slot_iso_utc

            current_day += timedelta(days=1)
            days_generated += 1

        return slots
