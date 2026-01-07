import logging
from datetime import datetime
from backend.core.postgres_client import PostgresManager

logger = logging.getLogger("PendingSaver")

# Initialize Postgres once
db = PostgresManager()


# ----------------------------------------------------
# VALIDATION
# ----------------------------------------------------

def _validate_reservation(res: dict) -> bool:
    required_keys = [
        "guest_name",
        "guest_phone",
        "date",
        "time",
        "guests",
        "special_requests",
    ]

    for k in required_keys:
        if k not in res:
            logger.warning(f"⚠️ Missing required field: {k}")
            return False

    return True


# ----------------------------------------------------
# PUBLIC API (USED BY SERVER + AGENTS)
# ----------------------------------------------------

def add_pending_reservation(cleaned_reservation: dict) -> bool:
    """
    Save a pending reservation directly to Postgres.
    """
    if not _validate_reservation(cleaned_reservation):
        return False

    try:
        # Prepare record
        raw_record = {
            "restaurant_id": cleaned_reservation.get("restaurant_id"),
            "guest_name": cleaned_reservation.get("guest_name"),
            "guest_phone": cleaned_reservation.get("guest_phone"),
            "date": cleaned_reservation.get("date"),
            "time": cleaned_reservation.get("time"),
            "guests": cleaned_reservation.get("guests"),
            "special_requests": cleaned_reservation.get("special_requests", ""),
            "source": "vapi",
            "status": "pending",
        }
        # Filter None values if needed, though Postgres JSONB can handle them or we can store as is.
        # But for consistency with previous logic which removed empty strings:
        record = {k: v for k, v in raw_record.items() if v not in [None, ""]}

        db.create_pending_reservation(record)

        # ----------------------------------------------------
        # 🟢 AUTO-CONFIRM (Dual Write)
        # ----------------------------------------------------
        if _validate_reservation(cleaned_reservation):
             # create_reservation in PostgresManager expects (restaurant_id, data)
             # passed 'record' has 'restaurant_id' but create_reservation might expect it separate or in data.
             # checking postgres_client.py: create_reservation(self, restaurant_id: str, data: dict)
             
            db.create_reservation(
                record.get("restaurant_id"),
                record # Pass the CLEANED dict
            )
            logger.info("✅ Reservation auto-confirmed and saved to main table")

        logger.info("✅ Pending reservation saved to Postgres")
        return True

    except Exception as e:
        logger.exception("❌ Failed to save pending reservation to Postgres")
        return False


def get_pending_reservations():
    """
    Fetch all pending reservations from Postgres.
    """
    try:
        return db.get_pending_reservations()
    except Exception:
        logger.exception("❌ Failed to fetch pending reservations")
        return []


def pop_next_reservation():
    """
    Fetch + delete the oldest pending reservation.
    """
    try:
        # get_oldest_pending_reservation returns dict with "id" and "fields"
        record = db.get_oldest_pending_reservation()

        if not record:
            return None

        db.delete_pending_reservation(record["id"])
        return record["fields"]

    except Exception:
        logger.exception("❌ Failed to pop pending reservation")
        return None


def clear_all():
    """
    Clear all pending reservations.
    """
    try:
        db.clear_pending_reservations()
        return True
    except Exception:
        logger.exception("❌ Failed to clear pending reservations")
        return False
