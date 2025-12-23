import os
import re
import logging
from typing import Optional

from pyairtable import Api
from pyairtable.formulas import match

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """
    Normalize phone numbers for matching:
    - Keep only digits.
    Example: '+1 (912) 737-0374' -> '19127370374'
    """
    if not phone:
        return ""
    return re.sub(r"\D", "", str(phone))


class AirtableManager:
    def __init__(self):
        self.api_key = os.environ.get("AIRTABLE_API_KEY")
        self.base_id = os.environ.get("AIRTABLE_BASE_ID")

        if not self.api_key or not self.base_id:
            logger.error(
                "❌ Airtable credentials missing. Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID."
            )

        self.api = Api(self.api_key) if self.api_key else None

        if self.api and self.base_id:
            self.restaurants = self.api.table(self.base_id, "Restaurants")
            self.reservations = self.api.table(self.base_id, "Reservations")
            self.pending = self.api.table(self.base_id, "PendingReservations")
            self.logs = self.api.table(self.base_id, "call logs")
        else:
            self.restaurants = None
            self.reservations = None
            self.pending = None
            self.logs = None

    # --------------------------------------------------
    # RESTAURANT LOOKUP
    # --------------------------------------------------

    def get_restaurant_by_phone(self, phone_number: str) -> Optional[dict]:
        if not self.restaurants:
            return None

        if not phone_number:
            return None

        if isinstance(phone_number, dict):
            phone_number = phone_number.get("number", "")

        try:
            clean_number = normalize_phone(phone_number)
            formula = match({"normalized_phone": clean_number})
            records = self.restaurants.all(formula=formula)
            return records[0] if records else None
        except Exception as e:
            logger.error(f"❌ Restaurant lookup failed: {e}")
            return None

    # --------------------------------------------------
    # CONFIRMED RESERVATIONS
    # --------------------------------------------------

    def create_reservation(self, restaurant_id: str, data: dict) -> bool:
        if not self.reservations:
            return False

        try:
            record = {
                **({"restaurant": [restaurant_id]} if restaurant_id else {}),
                "guest_name": data.get("guest_name"),
                "guest_phone": data.get("guest_phone", ""),
                "date": data.get("date"),
                "time": data.get("time"),
                "guests": int(data.get("guests", 1)),
                "special_requests": data.get("special_requests", ""),
                "status": "Confirmed",
            }

            self.reservations.create(record)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create reservation: {e}")
            return False

    # --------------------------------------------------
    # 🕒 PENDING RESERVATIONS (NEW)
    # --------------------------------------------------

    def create_pending_reservation(self, data: dict):
        if not self.pending:
            raise RuntimeError("PendingReservations table not initialized")

        return self.pending.create(data)

    def get_pending_reservations(self):
        if not self.pending:
            return []
        return self.pending.all()

    def get_oldest_pending_reservation(self):
        if not self.pending:
            return None

        records = self.pending.all(
            sort=[("created_at", "asc")],
            max_records=1
        )
        return records[0] if records else None

    def delete_pending_reservation(self, record_id: str):
        if not self.pending:
            return
        self.pending.delete(record_id)

    def clear_pending_reservations(self):
        if not self.pending:
            return
        for r in self.pending.all():
            self.pending.delete(r["id"])

    # --------------------------------------------------
    # LOGGING
    # --------------------------------------------------

    def log_call(self, data: dict):
        if not self.logs:
            return
        try:
            self.logs.create(data)
        except Exception as e:
            logger.error(f"❌ Call log failed: {e}")

    # --------------------------------------------------
    # BULK FETCHES
    # --------------------------------------------------

    def get_all_reservations(self):
        return self.reservations.all() if self.reservations else []

    def get_all_logs(self):
        return self.logs.all() if self.logs else []

    def get_all_restaurants(self):
        return self.restaurants.all() if self.restaurants else []

    def get_restaurant_by_id(self, restaurant_id: str):
        """
        restaurant_id here = your numeric/text restaurant_id column in Airtable (like 3)
        NOT the Airtable record id (recXXXX).
        """
        if not self.restaurants or not restaurant_id:
            return None
        try:
            formula = match({"restaurant_id": str(restaurant_id)})
            records = self.restaurants.all(formula=formula, max_records=1)
            return records[0] if records else None
        except Exception as e:
            logger.error(f"❌ get_restaurant_by_id failed: {e}")
            return None

    def get_call_logs_by_restaurant(self, restaurant_id: str):
        if not self.logs or not restaurant_id:
            return []
        try:
            formula = match({"restaurant_id": str(restaurant_id)})
            return self.logs.all(formula=formula)
        except Exception as e:
            logger.error(f"❌ get_call_logs_by_restaurant failed: {e}")
            return []

    def get_reservations_by_restaurant(self, restaurant_id: str):
        if not self.reservations or not restaurant_id:
            return []
        try:
            formula = match({"restaurant_id": str(restaurant_id)})
            return self.reservations.all(formula=formula)
        except Exception as e:
            logger.error(f"❌ get_reservations_by_restaurant failed: {e}")
            return []
