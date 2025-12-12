import re
import logging
from datetime import datetime

logger = logging.getLogger("TranscriptExtractor")


# ----------------------------------------------------
# BASIC CLEANERS
# ----------------------------------------------------

def clean_text(val):
    if not val:
        return ""
    return str(val).strip()


def clean_phone(s):
    if not s:
        return ""

    # extract digits, remove spaces & symbols
    digits = re.sub(r"[^\d]", "", s)

    # accept 7–15 digits
    if 7 <= len(digits) <= 15:
        return digits

    return ""


def clean_date(s):
    """
    Convert natural language date → YYYY-MM-DD
    Allowed formats:
        - 25 Dec 2025
        - Dec 25
        - tomorrow
        - today
        - 1/2/2025
    """
    if not s:
        return ""

    s = s.lower().strip()

    today = datetime.now()

    if "today" in s:
        return today.strftime("%Y-%m-%d")

    if "tomorrow" in s:
        return (today.replace(day=today.day + 1)).strftime("%Y-%m-%d")

    # numeric formats
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except:
            pass

    return s


def clean_time(s):
    """
    Convert natural language time → HH:MM (7pm → 19:00)
    """
    if not s:
        return ""

    s = s.lower().replace(" ", "").replace(".", "")

    match = re.match(r"^(\d{1,2})(:?(\d{2}))?(am|pm)?$", s)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(3)) if match.group(3) else 0
        ampm = match.group(4)

        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        return f"{hour:02d}:{minute:02d}"

    if re.match(r"^\d{2}:\d{2}$", s):
        return s

    return s


def extract_guests(s):
    if not s:
        return 2

    match = re.search(r"\b(\d{1,2})\b", s)
    if match:
        return int(match.group(1))

    return 2


# ----------------------------------------------------
# MASTER EXTRACTION FUNCTION
# ----------------------------------------------------

def extract_reservation(transcript_text: str, restaurant_id: str = None):
    """
    Extract guest_name, phone, date, time, guests, special_requests
    from full transcript text.
    """

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

    # ----------------------------
    # NAME
    # ----------------------------
    name_match = re.search(r"(my name is|this is|i am)\s+([a-zA-Z ]+)", text)
    if name_match:
        result["guest_name"] = clean_text(name_match.group(2))

    # ----------------------------
    # PHONE
    # ----------------------------
    phone_match = re.search(r"(\+?\d[\d \-]{6,})", text)
    if phone_match:
        result["guest_phone"] = clean_phone(phone_match.group(1))

    # ----------------------------
    # DATE
    # ----------------------------
    date_match = re.search(
        r"\b(?:for|on)\s+(today|tomorrow|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+[a-zA-Z]+)",
        text)
    if date_match:
        result["date"] = clean_date(date_match.group(1))

    # ----------------------------
    # TIME
    # ----------------------------
    time_match = re.search(r"\b(\d{1,2}(:?\d{2})?\s*(am|pm)?)\b", text)
    if time_match:
        result["time"] = clean_time(time_match.group(1))

    # ----------------------------
    # GUESTS
    # ----------------------------
    guests_match = re.search(r"(?:for|we are|people|guests)\s+(\d{1,2})", text)
    if guests_match:
        result["guests"] = int(guests_match.group(1))

    # ----------------------------
    # SPECIAL REQUESTS
    # ----------------------------
    special_match = re.search(
        r"(birthday|anniversary|vegan|allergic|gluten|no special requests|nothing special)",
        text,
    )
    if special_match:
        val = special_match.group(1)
        if "no" in val:
            result["special_requests"] = ""
        else:
            result["special_requests"] = val

    return result


# ----------------------------------------------------
# COMPATIBILITY WRAPPER (Fixes your ImportError)
# ----------------------------------------------------

def extract_reservation_from_transcript(transcript_text: str, restaurant_id: str = None):
    """
    Wrapper for older imports.
    Your server expects this function name.
    """
    return extract_reservation(transcript_text, restaurant_id)


__all__ = [
    "extract_reservation",
    "extract_reservation_from_transcript"
]
