from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from .database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    business_name = Column(String)
    full_name = Column(String)
    occupation = Column(String)
    phone = Column(String)
    password_hash = Column(String)
    status = Column(String, default="pending")
    # Link to a specific restaurant if this is a single-restaurant owner
    restaurant_id = Column(Integer, nullable=True) 
    created_at = Column(DateTime, default=datetime.utcnow)

class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(Integer, primary_key=True, index=True) # Auto-increment integer
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, index=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    reservations = relationship("Reservation", back_populates="restaurant")
    call_logs = relationship("CallLog", back_populates="restaurant")

class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    
    guest_name = Column(String)
    guest_phone = Column(String)
    date = Column(String) # Keeping as string 'YYYY-MM-DD' for simplicity or use Date
    time = Column(String) # Keeping as string 'HH:MM'
    guests = Column(Integer)
    special_requests = Column(Text)
    status = Column(String, default="Confirmed")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    restaurant = relationship("Restaurant", back_populates="reservations")

class PendingReservation(Base):
    __tablename__ = "pending_reservations"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(JSON) # Stores the flexible structure {guest_name, ...}
    created_at = Column(DateTime, default=datetime.utcnow)

class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"), nullable=True)
    
    call_uuid = Column(String, index=True)
    intent = Column(String)
    outcome = Column(String)
    agent_summary = Column(Text)
    recording_url = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    restaurant = relationship("Restaurant", back_populates="call_logs")
