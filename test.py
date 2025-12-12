"""
END-TO-END SYSTEM TEST
Simulates what happens AFTER a call ends.

Flow tested:
Transcript
→ extract_from_transcript
→ pending_reservations.json
→ background saver logic
→ Airtable
"""

import time
from pprint import pprint
from dotenv import load_dotenv

load_dotenv()

from src.core.extract_from_transcript import extract_reservation_from_transcript
from src.core.pending_saver import add_pending_reservation, pop_next_reservation
from src.core.reservation_mapper import normalize_reservation_data
from src.core.airtable_client import AirtableManager


# ---------------------------------------------------------
# CONFIG — USE A REAL RESTAURANT RECORD ID FROM AIRTABLE
# ---------------------------------------------------------
airtable = AirtableManager()

record = airtable.get_restaurant_by_phone("+19302629248")  # business phone
assert record, "Restaurant not found"

RESTAURANT_ID = record["id"]



# ---------------------------------------------------------
# FAKE CALL TRANSCRIPT (what VAPI would send)
# ---------------------------------------------------------
TRANSCRIPT = """
Hi, my name is Alex.
I want to book a table for tomorrow at 7pm.
We are 4 people.
My phone number is 91234 56789.
No special requests.
"""


def run_full_flow_test():
    print("\n🧪 STARTING FULL FLOW TEST\n")

    # -------------------------------------------------
    # 1️⃣ EXTRACT FROM TRANSCRIPT
    # -------------------------------------------------
    extracted = extract_reservation_from_transcript(
        TRANSCRIPT,
        restaurant_id=RESTAURANT_ID
    )

    print("📌 Extracted from transcript:")
    pprint(extracted)

    assert extracted["guest_name"]
    assert extracted["guest_phone"]
    assert extracted["date"]
    assert extracted["guests"]

    # -------------------------------------------------
    # 2️⃣ PUSH INTO PENDING QUEUE
    # -------------------------------------------------
    success = add_pending_reservation(extracted)
    assert success is True

    print("\n📥 Saved to pending_reservations.json")

    # -------------------------------------------------
    # 3️⃣ SIMULATE BACKGROUND SAVER PICKUP
    # -------------------------------------------------
    job = pop_next_reservation()
    assert job is not None

    print("\n📤 Background saver picked job:")
    pprint(job)

    # -------------------------------------------------
    # 4️⃣ NORMALIZE DATA (mapper)
    # -------------------------------------------------
    normalized = normalize_reservation_data(job)

    print("\n🔄 Normalized reservation:")
    pprint(normalized)

    # -------------------------------------------------
    # 5️⃣ SAVE TO AIRTABLE
    # -------------------------------------------------
    airtable = AirtableManager()

    success = airtable.create_reservation(
        restaurant_id=job.get("restaurant_id"),
        data=normalized
    )

    assert success is True

    print("\n✅ SUCCESS — Reservation saved to Airtable")
    print("🎉 FULL FLOW VERIFIED\n")


if __name__ == "__main__":
    run_full_flow_test()
