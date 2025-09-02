import logging
from datetime import date, datetime, timedelta
from typing import Annotated, Any
import json

import numpy as np
from semantic_kernel.functions import kernel_function, FunctionResult

from ..models.Deliveries import DeliverySlotModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DeliveryPlugin:
    """Delivery plugin for managing tasks related to scheduling or rescheduling order deliveries."""
    def __init__(self):
        self.current_verified_order_number = None

    @kernel_function
    def verify_identity_for_order(
        self,
        order_number: Annotated[int, "The ID of the order to verify (obtained from the customer)."],
        delivery_postcode: Annotated[str, "The delivery postcode for the order."],
        order_phone_number: Annotated[int | None, "The phone number associated with the order. Only required if initial verification fails due to phone number customer is calling from not matching order."] = None
    ) -> str:
        """Verify the customer's identity against the details on their order. This MUST be performed before any delivery actions can be performed."""
        logger.info(f"@ verify_identity called for order {order_number}, postcode {delivery_postcode}, phone {order_phone_number}")
        # TODO: retrieve order by order number
        # TODO: verify delivery postcode matches order postcode
        # TODO: get phone number from current ACS context and verify it matches order phone number
        self.current_verified_order_number = order_number
        return f"Customer has been verified against order {order_number}. Delivery actions against this order can now be performed."

    @kernel_function
    def zz_never_use_this(
        self,
        start_date: Annotated[str, "The start date for the delivery slots, defaulting to today. Use for pagination."] = date.today().isoformat(),
        range_in_days: Annotated[int, "The number of days to look ahead for delivery slots."] = 7
    ) -> str:
        """Get the slots that are available for delivery for the current verified order."""
        logger.info(f"@ get_available_slots_for_delivery called for {start_date} with range {range_in_days} days")

        base_date = datetime.fromisoformat(start_date)
        slot_datetime = base_date.strftime("%Y-%m-%d") +"T08:00:00.046Z"
        logger.info(f"@ get_available_slots_for_delivery - Simulating available slot for {slot_datetime}")
        response = [DeliverySlotModel(id="1", start_time=slot_datetime)]

        return response
    
    @kernel_function
    def get_available_slots_for_delivery(
        self,
        start_date: Annotated[str, "The start date for the delivery slots, defaulting to today. Use for pagination."] = date.today().isoformat(),
        range_in_days: Annotated[int, "The number of days to look ahead for delivery slots."] = 7
    ) -> str:
        """Get the slots that are available for delivery for the current verified order."""
        logger.info(f"@ get_available_slots_for_delivery called for {start_date} with range {range_in_days} days")

        if not self.current_verified_order_number:
            logger.warning("Attempted to get available slots without verifying identity.")
            raise ValueError("Please verify customer's identity before getting available delivery slots.")

        # Simulate getting available slots for the order
        # Get between 0 and 10 random slots in the provided date range
        slots = []
        # Build candidate slots across the date range (two per day for now)
        candidates: list[str] = []
        days = max(0, int(range_in_days))
        base_date = date.fromisoformat(start_date)
        for i in range(days):
            slot_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
            candidates.append(f"{slot_date}T08:00:00.046Z")
            candidates.append(f"{slot_date}T10:00:00.046Z")

        if not candidates:
            logger.debug(f"@ get_available_slots_for_delivery returning no slots [] for {start_date} with range {range_in_days} days")
            return "No slots available"

        # Randomly select between 0 and 10 unique slots from candidates
        max_n = min(10, len(candidates))
        n = int(np.random.randint(0, max_n + 1))  # inclusive upper bound
        if n == 0:
            logger.debug(f"@ get_available_slots_for_delivery 2 returning no slots [] for {start_date} with range {range_in_days} days")
            return "No slots available"

        chosen_idxs = np.random.choice(len(candidates), size=n, replace=False)
        # Sort for a stable, chronological order in the response
        chosen_times = [candidates[i] for i in sorted(chosen_idxs)]

        slots = [DeliverySlotModel(id=str(idx + 1), start_time=t) for idx, t in enumerate(chosen_times)]
        #slots_json = json.dumps([slot.model_dump() for slot in slots])
        slots_json = json.dumps(slots)

        logger.debug(f"@ get_available_slots_for_delivery returning slots successfully {start_date} with range {range_in_days} days")
        logger.info(f"@ get_available_slots_for_delivery returning slots {slots_json}")

        return slots_json

    @kernel_function
    def schedule_delivery(
        self,
        slot_id: Annotated[str, "The ID of the delivery slot to schedule, retrieved from available slots."]
    ) -> str:
        """Schedule a delivery for the customer's order."""
        logger.info(f"@ schedule_delivery called for id {slot_id}")

        if not self.current_verified_order_number:
            logger.warning("Attempted to schedule delivery without verifying identity.")
            raise ValueError("Please verify customer's identity before scheduling a delivery.")

        return f"Delivery has been scheduled for slot {slot_id}."
