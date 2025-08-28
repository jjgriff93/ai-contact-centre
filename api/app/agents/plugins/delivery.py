import logging
from datetime import date, datetime, timedelta
from typing import Annotated, Any

import numpy as np
from semantic_kernel.functions import kernel_function

from ..models.Deliveries import DeliverySlotModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeliveryPlugin:
    """Delivery plugin for managing tasks related to scheduling or rescheduling order deliveries."""

    @kernel_function
    def get_available_slots_for_delivery(
        self,
        order_number: Annotated[str, "The order number to get delivery slots for."],
        start_date: Annotated[str, "The start date for the delivery slots in ISO format, defaulting to today. Use for pagination."] = date.today().isoformat(),
        range_in_days: Annotated[int, "The number of days to look ahead for delivery slots."] = 7
    ) -> list[DeliverySlotModel]:
        """Get the slots that are available for delivery."""
        logger.info(f"@ get_available_slots_for_delivery called for order {order_number} from {start_date} with range {range_in_days} days")

        # Simulate getting available slots for the order
        # Get between 0 and 10 random slots in the provided date range
        slots = []
        # Build candidate slots across the date range (two per day for now)
        candidates: list[str] = []
        days = max(0, int(range_in_days))
        # TODO: Ensure date is in iso format in case the model passes the wrong format

        base_date = date.fromisoformat(start_date)
        for i in range(days):
            slot_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            candidates.append(f"{slot_date}T08:00:00.046Z")
            candidates.append(f"{slot_date}T10:00:00.046Z")

        if not candidates:
            return []

        # Randomly select between 0 and 10 unique slots from candidates
        max_n = min(10, len(candidates))
        n = int(np.random.randint(0, max_n + 1))  # inclusive upper bound
        if n == 0:
            return []

        chosen_idxs = np.random.choice(len(candidates), size=n, replace=False)
        # Sort for a stable, chronological order in the response
        chosen_times = [candidates[i] for i in sorted(chosen_idxs)]

        slots = [DeliverySlotModel(id=str(idx + 1), start_time=t) for idx, t in enumerate(chosen_times)]

        return slots
    
    @kernel_function
    def schedule_delivery(
        self,
        slot_id: Annotated[str, "The ID of the delivery slot to schedule, retrieved from available slots."]
    ) -> str:
        """Schedule a delivery for the customer's order."""
        logger.info(f"@ schedule_delivery called for id {slot_id}")

        return f"Delivery has been scheduled for slot {slot_id}."
