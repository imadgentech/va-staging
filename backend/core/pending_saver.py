import logging
from datetime import datetime
from backend.core.airtable_client import AirtableManager

logger = logging.getLogger("PendingSaver")

# Initialize Airtable once
airtable = AirtableManager()


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
    Save a pending reservation directly to Airtable.
    """
    if not _validate_reservation(cleaned_reservation):
        return False

    try:
        record = {
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

        airtable.create_pending_reservation(record)

        # ----------------------------------------------------
        # 🟢 AUTO-CONFIRM (Dual Write)
        # The user requested that data "transfer" to Reservations.
        # Since we don't have a manual review step, we write to BOTH.
        # ----------------------------------------------------
        if _validate_reservation(cleaned_reservation):
            airtable.create_reservation(
                cleaned_reservation.get("restaurant_id"),
                cleaned_reservation
            )
            logger.info("✅ Reservation auto-confirmed and saved to main table")

        logger.info("✅ Pending reservation saved to Airtable")
        return True

    except Exception as e:
        logger.exception("❌ Failed to save pending reservation to Airtable")
        return False


def get_pending_reservations():
    """
    Fetch all pending reservations from Airtable.
    (Optional — used by micro-agents if needed)
    """
    try:
        return airtable.get_pending_reservations()
    except Exception:
        logger.exception("❌ Failed to fetch pending reservations")
        return []


def pop_next_reservation():
    """
    Fetch + delete the oldest pending reservation.
    """
    try:
        record = airtable.get_oldest_pending_reservation()

        if not record:
            return None

        airtable.delete_pending_reservation(record["id"])
        return record["fields"]

    except Exception:
        logger.exception("❌ Failed to pop pending reservation")
        return None


def clear_all():
    """
    Clear all pending reservations.
    """
    try:
        airtable.clear_pending_reservations()
        return True
    except Exception:
        logger.exception("❌ Failed to clear pending reservations")
        return False
