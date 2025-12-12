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
            logger.error("❌ Airtable credentials missing in .env. Please set AIRTABLE_API_KEY and AIRTABLE_BASE_ID.")
            # We allow it to continue so the app doesn't crash, but functionality will be broken.


        self.api = Api(self.api_key) if self.api_key else None

        # Connect to specific tables
        if self.api and self.base_id:
            self.restaurants = self.api.table(self.base_id, "Restaurants")
            self.reservations = self.api.table(self.base_id, "Reservations")
            self.logs = self.api.table(self.base_id, "call logs")
        else:
            self.restaurants = None
            self.reservations = None
            self.logs = None

    # ---------- LOOKUP BY BUSINESS PHONE (CALLED NUMBER) ----------

    def get_restaurant_by_phone(self, phone_number: str) -> Optional[dict]:
        """
        Finds a restaurant by the business/Vapi number that was CALLED.
        Returns the full record (id + fields).

        Uses the `normalized_phone` field in Airtable for matching.
        """
        if not self.restaurants:
            logger.error("Restaurants table is not initialized")
            return None

        if not phone_number:
            logger.warning("Received call with NO business phone number")
            return None

        # Handle dicts defensively (in case caller passes the whole phone object)
        if isinstance(phone_number, dict):
            phone_number = phone_number.get("number", "")

        try:
            clean_number = normalize_phone(phone_number)
            logger.info(
                f"Looking up restaurant for phone: {phone_number} -> {clean_number}"
            )

            # Match on normalized_phone (digits only)
            formula = match({"normalized_phone": clean_number})
            records = self.restaurants.all(formula=formula)

            if records:
                logger.info(f"Found restaurant for {phone_number}")
                return records[0]

            logger.warning(f"No restaurant found for phone: {phone_number}")
            return None

        except Exception as e:
            if "422" in str(e) or "INVALID_VALUE" in str(e):
                 logger.error(f"❌ Airtable Error: Possible missing 'normalized_phone' field in Restaurants table. Details: {e}")
            else:
                logger.error(f"Error fetching restaurant: {e}")
            return None

    # ---------- RESERVATIONS ----------

    def create_reservation(self, restaurant_id: str, data: dict) -> bool:
        """
        Creates a new reservation linked to the restaurant.
        """
        if not self.reservations:
            logger.error("❌ Reservations table is not initialized (check AIRTABLE_BASE_ID / table name).")
            return False

        try:
            logger.info(f"📝 Creating reservation | restaurant_id={restaurant_id} | data={data}")

            record = {
                # Only set link field if we have a valid restaurant_id
                # (avoids 422 errors if restaurant lookup failed)
                **({"restaurant": [restaurant_id]} if restaurant_id else {}),
                "guest_name": data.get("guest_name"),
                "guest_phone": data.get("guest_phone", "N/A"),
                "date": data.get("date"),
                "time": data.get("time"),
                "guests": int(data.get("guests", 1)),
                "special_requests": data.get("special_requests", ""),
                "status": "Confirmed",
            }

            self.reservations.create(record)
            logger.info("✅ Airtable reservation created successfully.")
            return True

        except Exception as e:
            logger.error(f"❌ Error creating reservation in Airtable: {e}")
            return False


    # ---------- LOGGING ----------

    def log_call(self, data: dict):
        """
        Logs a call summary and recording.
        """
        if not self.logs:
            logger.error("Logs table is not initialized")
            return

        try:
            self.logs.create(data)
            logger.info("Call logged successfully.")
        except Exception as e:
            logger.error(f"Error logging call: {e}")

    # ---------- BULK FETCHES ----------

    def get_all_reservations(self):
        if not self.reservations:
            return []
        return self.reservations.all()

    def get_all_logs(self):
        if not self.logs:
            return []
        try:
            return self.logs.all(sort=["-timestamp"])
        except Exception:
            return self.logs.all()

    def get_all_restaurants(self):
        if not self.restaurants:
            return []
        return self.restaurants.all()
