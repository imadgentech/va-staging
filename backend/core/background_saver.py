import time
import logging
from dotenv import load_dotenv

load_dotenv()

from backend.core.pending_saver import pop_next_reservation
from backend.core.airtable_client import AirtableManager
from backend.core.reservation_mapper import normalize_reservation_data

logger = logging.getLogger("BackgroundSaver")
logger.setLevel(logging.INFO)


# ----------------------------------------------------
# PROCESS SINGLE JOB
# ----------------------------------------------------

def process_job(job: dict, airtable: AirtableManager):
    """
    Processes a single reservation job and saves it to Airtable.

    job example:
    {
        "restaurant_id": "recXXXX",   # optional
        "guest_name": "...",
        "guest_phone": "...",
        "date": "...",
        "time": "...",
        "guests": 3,
        "special_requests": "..."
    }
    """

    restaurant_id = job.get("restaurant_id")

    # Normalize fields (7pm → 19:00, phone cleanup, etc.)
    normalized = normalize_reservation_data(job)
    logger.info(f"🔄 Normalized payload: {normalized}")

    airtable_payload = {
        "guest_name": normalized["guest_name"],
        "guest_phone": normalized["guest_phone"],
        "date": normalized["date"],
        "time": normalized["time"],
        "guests": normalized["guests"],
        "special_requests": normalized["special_requests"],
        "status": "Confirmed",
    }

    logger.info(f"📤 Saving reservation to Airtable: {airtable_payload}")

    success = airtable.create_reservation(
        restaurant_id=restaurant_id,
        data=airtable_payload
    )

    if not success:
        raise Exception("Airtable create_reservation() returned False")

    logger.info("✅ Reservation successfully saved to Airtable")


# ----------------------------------------------------
# MAIN LOOP
# ----------------------------------------------------

def run_background_saver():
    """
    Continuously pulls jobs from the pending queue
    and saves them to Airtable.
    """

    airtable = AirtableManager()
    logger.info("🚀 Background Saver started — listening for pending reservations...")

    while True:
        job = pop_next_reservation()

        if not job:
            time.sleep(1)
            continue

        try:
            process_job(job, airtable)
        except Exception as e:
            logger.error(f"❌ Failed processing job, will retry later: {e}")
            # NOTE: job is already removed from queue
            # If you want retries, add a retry queue later

        time.sleep(0.2)


# ----------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------

if __name__ == "__main__":
    run_background_saver()
