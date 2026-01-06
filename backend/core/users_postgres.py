import logging
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import User

logger = logging.getLogger(__name__)

class UsersPostgres:
    def __init__(self):
        pass

    def get_db(self):
        return SessionLocal()

    def create_user(self, data: dict):
        db: Session = self.get_db()
        try:
            # Check exist first?
            existing = db.query(User).filter(User.email == data["email"]).first()
            if existing:
                # Update? Or fail? For now, we assume signup = new. 
                # Or updating info if exists.
                pass 

            new_user = User(
                id=str(uuid.uuid4()),
                email=data["email"],
                business_name=data["business_name"],
                full_name=data["full_name"],
                occupation=data["occupation"],
                phone=data["phone"],
                password_hash=data.get("password", ""), # Hashed pass passed in
                status="pending"
            )
            db.add(new_user)
            db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            db.rollback()
            raise e
        finally:
            db.close()

    def get_user_by_email(self, email: str):
        if not email:
            return None
        
        db: Session = self.get_db()
        try:
            user = db.query(User).filter(User.email == email.lower()).first()
            if user:
                # Return dict structure compatible with old code
                return {
                    "fields": {
                        "email": user.email,
                        "password": user.password_hash,
                        "status": user.status,
                        "restaurant_id": user.restaurant_id,
                        # ... other fields if needed
                    }
                }
            return None
        finally:
            db.close()
