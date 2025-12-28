import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("TranscriptExtractor")

# ----------------------------------------------------
# BASIC CLEANERS
# ----------------------------------------------------

def clean_text(val):
    return str(val).strip() if val else ""


def clean_phone(s):
    if not s:
        return ""
    digits = re.sub(r"[^\d]", "", s)
    return digits if 7 <= len(digits) <= 15 else ""


# ----------------------------------------------------
# DATE HANDLING (STRICT & SAFE)
# ----------------------------------------------------

def clean_date(raw: str):
    """
    Convert natural language date → YYYY-MM-DD

    Supported:
    - today
    - tomorrow
    - day after tomorrow
    - in N days
    - after N days
    - 25 Dec 2025
    - 1/2/2025
    """

    if not raw:
        return ""

    raw = raw.lower().strip()
    today = datetime.now().date()

    # --- Relative days ---
    if raw == "today":
        return today.isoformat()

    if raw == "tomorrow":
        return (today + timedelta(days=1)).isoformat()

    if "day after tomorrow" in raw:
        return (today + timedelta(days=2)).isoformat()

    match = re.search(r"(in|after)\s+(\d+)\s+days?", raw)
    if match:
        days = int(match.group(2))
        return (today + timedelta(days=days)).isoformat()

    # --- Absolute formats ---
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass

    # ❌ Anything else is unsafe
    logger.warning(f"Invalid date phrase ignored: {raw}")
    return ""


# ----------------------------------------------------
# TIME
# ----------------------------------------------------

def clean_time(s):
    if not s:
        return ""

    s = s.lower().replace(" ", "").replace(".", "")
    match = re.match(r"^(\d{1,2})(:?(\d{2}))?(am|pm)?$", s)

    if match:
        hour = int(match.group(1))
        minute = int(match.group(3) or 0)
        ampm = match.group(4)

        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0

        return f"{hour:02d}:{minute:02d}"

    return ""


def extract_guests(text):
    # Strict: requires "guests", "people", "party of", etc.
    # Matches: "6 guests", "party of 6", "6 people"
    match = re.search(r"\b(\d{1,2})\s*(people|guests|persons|pax)\b", text)
    if not match:
        # Try "party of X"
        match = re.search(r"\bparty of\s*(\d{1,2})\b", text)

    return int(match.group(1)) if match else 2

# ----------------------------------------------------
# MASTER EXTRACTION FUNCTION
# ----------------------------------------------------

def extract_reservation(transcript_text: str, restaurant_id: str = None):
    result = {
        "restaurant_id": restaurant_id,
        "guest_name": "",
        "guest_phone": "",
        "date": "",
        "time": "",
        "guests": 2,
        "special_requests": ""
    }

    text = transcript_text.lower()

    # NAME
    name_match = re.search(r"(my name is|this is|i am)\s+([a-zA-Z ]+)", text)
    if name_match:
        result["guest_name"] = clean_text(name_match.group(2))

    # PHONE
    phone_match = re.search(r"(\+?\d[\d \-]{6,})", text)
    if phone_match:
        result["guest_phone"] = clean_phone(phone_match.group(1))

    # DATE (STRICT)
    date_match = re.search(
        r"(today|tomorrow|day after tomorrow|in \d+ days|after \d+ days|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+[a-zA-Z]+)",
        text
    )
    if date_match:
        result["date"] = clean_date(date_match.group(1))

    # TIME - STRICTER: Needs AM/PM or :MM
    # preventing "20" from "20th" matching as 8pm
    time_match = re.search(r"\b(\d{1,2}:\d{2}\s*(am|pm)?|\d{1,2}\s*(am|pm))\b", text)
    if time_match:
        result["time"] = clean_time(time_match.group(0))

    # GUESTS
    result["guests"] = extract_guests(text)

    # SPECIAL REQUESTS
    special_match = re.search(
        r"(birthday|anniversary|vegan|allergic|gluten|nothing special|no special requests)",
        text
    )
    if special_match and "no" not in special_match.group(1):
        result["special_requests"] = special_match.group(1)

    return result


# ----------------------------------------------------
# COMPATIBILITY WRAPPER
# ----------------------------------------------------

def extract_reservation_from_transcript(transcript_text: str, restaurant_id: str = None):
    return extract_reservation(transcript_text, restaurant_id)


__all__ = [
    "extract_reservation",
    "extract_reservation_from_transcript"
]
