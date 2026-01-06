import logging
import re
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .database import SessionLocal
from .models import Restaurant, Reservation, PendingReservation, CallLog

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

class PostgresManager:
    def __init__(self):
        # We use a fresh session per method or handle it here. 
        # For simple migration, let's open sessions on demand to avoid thread issues if single instance.
        pass

    def get_db(self):
        return SessionLocal()

    # --------------------------------------------------
    # RESTAURANT LOOKUP
    # --------------------------------------------------

    def get_restaurant_by_phone(self, phone_number: str) -> Optional[dict]:
        if not phone_number:
            return None

        if isinstance(phone_number, dict):
            phone_number = phone_number.get("number", "")

        clean_number = normalize_phone(phone_number)
        
        db: Session = self.get_db()
        try:
            # We filter by checking if normalized phone matches. 
            # Ideally standardizing DB storage is better, but here we scan or assume match.
            # For strict equality:
            restaurant = db.query(Restaurant).filter(Restaurant.phone_number == clean_number).first()
            
            if restaurant:
                # Convert to dict format expected by callers
                return {
                    "fields": {
                        "restaurant_id": restaurant.id,
                        "name": restaurant.name,
                        "phone_number": restaurant.phone_number
                    }
                }
            return None
        except Exception as e:
            logger.error(f"❌ Restaurant lookup failed: {e}")
            return None
        finally:
            db.close()

    # --------------------------------------------------
    # CONFIRMED RESERVATIONS
    # --------------------------------------------------

    def create_reservation(self, restaurant_id: str, data: dict) -> bool:
        db: Session = self.get_db()
        try:
            res = Reservation(
                restaurant_id=int(restaurant_id) if restaurant_id else None,
                guest_name=data.get("guest_name"),
                guest_phone=data.get("guest_phone", ""),
                date=data.get("date"),
                time=data.get("time"),
                guests=int(data.get("guests", 1)),
                special_requests=data.get("special_requests", ""),
                status="Confirmed",
            )
            db.add(res)
            db.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create reservation: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    # --------------------------------------------------
    # 🕒 PENDING RESERVATIONS
    # --------------------------------------------------

    def create_pending_reservation(self, data: dict):
        db: Session = self.get_db()
        try:
            pending = PendingReservation(data=data)
            db.add(pending)
            db.commit()
            db.refresh(pending)
            # Return dict format similar to Airtable response
            return {"id": pending.id, "fields": pending.data, "createdTime": str(pending.created_at)}
        except Exception as e:
            logger.error(f"❌ Failed to create pending reservation: {e}")
            db.rollback()
            raise e
        finally:
            db.close()

    def get_pending_reservations(self):
        db: Session = self.get_db()
        try:
            records = db.query(PendingReservation).all()
            return [
                {"id": r.id, "fields": r.data, "createdTime": str(r.created_at)}
                for r in records
            ]
        finally:
            db.close()

    def get_oldest_pending_reservation(self):
        db: Session = self.get_db()
        try:
            record = db.query(PendingReservation).order_by(PendingReservation.created_at.asc()).first()
            if record:
                return {"id": record.id, "fields": record.data, "createdTime": str(record.created_at)}
            return None
        finally:
            db.close()

    def delete_pending_reservation(self, record_id):
        db: Session = self.get_db()
        try:
            record = db.query(PendingReservation).filter(PendingReservation.id == record_id).first()
            if record:
                db.delete(record)
                db.commit()
        except:
            db.rollback()
        finally:
            db.close()

    def clear_pending_reservations(self):
        db: Session = self.get_db()
        try:
            db.query(PendingReservation).delete()
            db.commit()
        except:
            db.rollback()
        finally:
            db.close()

    # --------------------------------------------------
    # LOGGING
    # --------------------------------------------------

    def log_call(self, data: dict):
        db: Session = self.get_db()
        try:
            log = CallLog(
                restaurant_id=int(data.get("restaurant_id")) if data.get("restaurant_id") else None,
                call_uuid=data.get("call_id"), # map call_id -> call_uuid
                intent=data.get("intent"),
                outcome=data.get("outcome"),
                agent_summary=data.get("agent_summary"),
                recording_url=data.get("recording_url"),
                timestamp=None # let DB handle default or parse data.get("timestamp")
            )
            # if timestamp string provided, try to parse? Or rely on default created_at?
            # data['timestamp'] in original was likely iso string.
            db.add(log)
            db.commit()
        except Exception as e:
            logger.error(f"❌ Call log failed: {e}")
        finally:
            db.close()

    # --------------------------------------------------
    # BULK FETCHES
    # --------------------------------------------------

    def get_restaurant_by_id(self, restaurant_id: str):
        if not restaurant_id:
            return None
        db: Session = self.get_db()
        try:
            # Here restaurant_id is the ID primary key
            r = db.query(Restaurant).filter(Restaurant.id == int(restaurant_id)).first()
            if r:
                return {
                    "fields": {
                        "restaurant_id": r.id,
                        "name": r.name,
                        "phone_number": r.phone_number
                    }
                }
            return None
        except Exception as e:
             logger.error(f"❌ get_restaurant_by_id failed: {e}")
             return None
        finally:
            db.close()

    def get_call_logs_by_restaurant(self, restaurant_id: str):
        if not restaurant_id:
            return []
        
        db: Session = self.get_db()
        try:
            logs = db.query(CallLog).filter(CallLog.restaurant_id == int(restaurant_id)).all()
            return [
                {
                    "fields": {
                        "call_id": l.call_uuid,
                        "intent": l.intent,
                        "outcome": l.outcome,
                        "agent_summary": l.agent_summary,
                        "recording_url": l.recording_url,
                        "timestamp": str(l.timestamp), # Convert to string for frontend
                        "created_at": str(l.timestamp) # for stats
                    }
                }
                for l in logs
            ]
        finally:
            db.close()
