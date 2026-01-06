import logging
import json
import os
from dotenv import load_dotenv

# LOAD ENV VARS FIRST
load_dotenv(override=True)
from jose import jwt, JWTError
from fastapi import Header
JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALGO = "HS256"
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi import HTTPException
from pydantic import BaseModel
from backend.core.users_postgres import UsersPostgres
from backend.core.postgres_client import PostgresManager
from backend.core.models import Base
from backend.core.database import engine
from backend.core.prompts import build_system_prompt
from backend.core.reservation_mapper import router as reservation_mapper_router
from backend.core.pending_saver import add_pending_reservation
from backend.core.extract_from_transcript import extract_reservation_from_transcript
from fastapi.middleware.cors import CORSMiddleware
import random
import time
import requests
# ---------------- OTP STORE (email -> {otp, expires_at}) ----------------
OTP_STORE = {}
OTP_EXPIRY_SECONDS = 300  # 5 minutes

# ---------------------------------------------------------
# INIT
# ---------------------------------------------------------
app = FastAPI(title="Voice Orchestrator")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Server")

app.include_router(reservation_mapper_router, prefix="")

# Startup DB
if engine:
    Base.metadata.create_all(bind=engine)

try:
    db_client = PostgresManager()
    logger.info("✅ Postgres connection established")
except Exception as e:
    logger.error(f"❌ Postgres init failed: {e}")
    db_client = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# AUTH (Password)
# ---------------------------------------------------------
import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_access_token(data: dict):
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGO)

# ... (Existing helper functions like extract_dialed_number, resolve_restaurant kept above or below correctly) ...
# To minimize diff noise, I will keep helper functions in their existing blocks if possible, 
# but I need to replace the EMAIL section and OTP endpoints.

# ---------------------------------------------------------
# SIGNUP
# ---------------------------------------------------------
class SignupPayload(BaseModel):
    business_name: str
    full_name: str
    occupation: str
    email: str
    phone: str
    password: str

try:
    users_db = UsersPostgres()
    logger.info("✅ Users DB ready")
except Exception as e:
    logger.error(f"❌ Users DB init failed: {e}")
    users_db = None

@app.post("/signup")
def signup_user(payload: SignupPayload):
    if not users_db:
        raise HTTPException(status_code=500, detail="Users DB unavailable")

    try:
        data = payload.dict()
        data["email"] = data["email"].lower().strip()
        
        # Hash password before storing
        raw_password = data.pop("password")
        data["password"] = hash_password(raw_password)

        users_db.create_user(data)
        return {"status": "ok"}
    except Exception as e:
        logger.exception("❌ Signup failed")
        raise HTTPException(status_code=500, detail="Signup failed")

# ---------------------------------------------------------
# LOGIN (Email + Password)
# ---------------------------------------------------------
class LoginPayload(BaseModel):
    email: str
    password: str

@app.post("/auth/login")
def login(payload: LoginPayload):
    email = payload.email.lower().strip()
    password = payload.password.strip()

    # 1. Fetch User
    user = users_db.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    fields = user.get("fields", {})
    stored_hash = fields.get("password", "")

    # 2. Verify Password
    if hash_password(password) != stored_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # 3. Check Status & Restaurant Link
    # We return the status/id so frontend can decide where to route (Dashboard vs Pending Screen)
    status = fields.get("status", "pending") # done / pending
    restaurant_id = fields.get("restaurant_id")

    return {
        "status": "success",
        "email": email,
        "user_status": status,
        "restaurant_id": restaurant_id,
        # "token": create_access_token({"sub": email}) # Optional if you need JWT later
    }

@app.get("/dashboard/call-logs/{restaurant_id}")
def get_call_logs_for_dashboard(restaurant_id: str):
    if not db_client:
        raise HTTPException(status_code=500, detail="DB not available")

    # 🔒 Ensure restaurant actually exists
    restaurant = db_client.get_restaurant_by_id(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    logs = db_client.get_call_logs_by_restaurant(restaurant_id)

    # Normalize response for frontend
    return {
        "restaurant_id": restaurant_id,
        "count": len(logs),
        "logs": [
            {
                "call_id": r["fields"].get("call_id"),
                "intent": r["fields"].get("intent"),
                "outcome": r["fields"].get("outcome"),
                "agent_summary": r["fields"].get("agent_summary"),
                "recording_url": r["fields"].get("recording_url"),
                "timestamp": r["fields"].get("timestamp"),
            }
            for r in logs
        ]
    }

@app.get("/dashboard/stats/{restaurant_id}")
def get_dashboard_stats(restaurant_id: str):
    records = db_client.get_call_logs_by_restaurant(restaurant_id)

    total_calls = len(records)

    missed_calls = sum(
        1 for r in records
        if r["fields"].get("outcome") == "missed"
    )

    # -------- Hourly breakdown --------
    hourly = {}
    for r in records:
        ts = r["fields"].get("created_at")
        if not ts:
            continue
        hour = ts[11:13]  # "HH" from ISO timestamp
        hourly[hour] = hourly.get(hour, 0) + 1

    by_hour = [
        {"hour": h, "calls": c}
        for h, c in sorted(hourly.items())
    ]

    # -------- Intent breakdown --------
    intent_map = {}
    for r in records:
        intent = r["fields"].get("intent", "Unknown")
        intent_map[intent] = intent_map.get(intent, 0) + 1

    intent_breakdown = [
        {"intent": k, "count": v}
        for k, v in intent_map.items()
    ]

    return {
        "total_calls": total_calls,
        "missed_calls": missed_calls,
        "by_hour": by_hour,
        "intent_breakdown": intent_breakdown
    }
