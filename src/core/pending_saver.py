import json
import os
import threading

LOCK = threading.Lock()
FILE_PATH = "pending_reservations.json"


# ----------------------------------------------------
# INTERNAL HELPERS
# ----------------------------------------------------

def _ensure_file_exists():
    """Create empty JSON array file if missing."""
    if not os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
        except Exception:
            pass


def _load_all():
    """Load existing pending reservations with corruption handling."""
    _ensure_file_exists()

    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        # If corrupted → reset file
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        return []


def _save_all(data):
    """Atomic write to prevent corruption."""
    temp_path = FILE_PATH + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    os.replace(temp_path, FILE_PATH)


# ----------------------------------------------------
# RESERVATION QUEUE FUNCTIONS
# ----------------------------------------------------

def _validate_reservation(res: dict) -> bool:
    """
    Ensure the JSON structure is correct before saving.
    restaurant_id is optional.
    """
    required_keys = ["guest_name", "guest_phone", "date", "time", "guests", "special_requests"]

    for k in required_keys:
        if k not in res:
            return False

    return True


def add_pending_reservation(cleaned_reservation: dict):
    """
    Add a normalized reservation to the queue.
    Supports optional:
        - restaurant_id
    """
    with LOCK:
        if not _validate_reservation(cleaned_reservation):
            return False

        data = _load_all()
        data.append(cleaned_reservation)
        _save_all(data)
        return True


def get_pending_reservations():
    """Return all pending reservations."""
    with LOCK:
        return _load_all()


def pop_next_reservation():
    """
    Remove and return the next reservation for saving.
    Returns None if queue is empty.
    """
    with LOCK:
        data = _load_all()

        if not data:
            return None

        next_item = data.pop(0)
        _save_all(data)
        return next_item


def clear_all():
    """Delete all pending reservations."""
    with LOCK:
        _save_all([])
        return True
