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
from backend.core.users_airtable import UsersAirtable
from backend.core.airtable_client import AirtableManager
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

try:
    airtable = AirtableManager()
    logger.info("✅ Airtable connection established")
except Exception as e:
    logger.error(f"❌ Airtable init failed: {e}")
    airtable = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def send_otp_email(to_email: str, otp: str):
    res = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Imadgen <onboarding@resend.dev>",
            "to": [to_email],
            "subject": "Your Imadgen Login Code",
            "html": f"""
                <p>Your login code is:</p>
                <h2>{otp}</h2>
                <p>Valid for 5 minutes.</p>
            """
        }
    )
    res.raise_for_status()

def create_access_token(data: dict):
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGO)

def decode_access_token(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])

# ---------------------------------------------------------
# EXTRACT BUSINESS NUMBER
# ---------------------------------------------------------
def extract_dialed_number(message: dict) -> str:
    call = message.get("call", {}) or {}

    pn = call.get("phoneNumber")
    if isinstance(pn, dict):
        return pn.get("number")
    if isinstance(pn, str):
        return pn

    to = call.get("to")
    if isinstance(to, dict):
        return to.get("number")
    if isinstance(to, str):
        return to

    top = message.get("phoneNumber")
    if isinstance(top, dict):
        return top.get("number")
    if isinstance(top, str):
        return top

    return None


# ---------------------------------------------------------
# RESOLVE BUSINESS + PROMPT
# ---------------------------------------------------------
def resolve_restaurant_and_prompt(dialed_number: str):
    if not airtable:
        return None, None, None

    record = airtable.get_restaurant_by_phone(dialed_number)
    if not record:
        logger.warning(f"⚠️ Unknown dialed number {dialed_number}")
        return None, None, None

    fields = record.get("fields", {}) or {}
    name = fields.get("name", "Business")

    system_prompt = build_system_prompt(fields)
    now_str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    system_prompt = f"CURRENT DATE/TIME: {now_str}\n\n{system_prompt}"

    return record, name, system_prompt


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------
@app.get("/")
def health_check():
    return {"status": "online", "service": "Vapi Orchestrator"}

@app.get("/inbound")
def inbound_health():
    return {"status": "ready", "message": "POST call events here"}

# ---------------------------------------------------------
# MAIN WEBHOOK
# ---------------------------------------------------------
@app.post("/inbound")
async def vapi_webhook(request: Request):
    payload = await request.json()

    # Save last request for debugging
    try:
        with open("last_vapi_request.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except:
        pass

    message = payload.get("message", {}) or {}
    msg_type = message.get("type")

    logger.info(f"🔔 Incoming message type={msg_type}")

    # ---------------------------------------------------------
    # 🎯 END OF CALL — PROCESS TRANSCRIPT
    # ---------------------------------------------------------
    if msg_type == "end-of-call-report":
        logger.info("📜 Processing end-of-call transcript...")

        transcript = message.get("transcript", "")

        if not transcript:
            logger.warning("⚠️ No transcript found in end-of-call-report")
            return {}

        # Extract restaurant_id FIRST
        dialed_number = extract_dialed_number(message)
        restaurant_id = None

        if dialed_number:
            record = airtable.get_restaurant_by_phone(dialed_number)
            restaurant_id = record.get("id") if record else None

        # Extract reservation data from transcript
        extracted = extract_reservation_from_transcript(transcript, restaurant_id)

        if not extracted:
            logger.warning("⚠️ No reservation data extracted from transcript")
            return {}

        logger.info(f"📌 Extracted reservation: {extracted}")

        # Save to pending queue (and auto-confirm)
        add_pending_reservation(extracted)

        # ---------------------------------------------------------
        # 📝 LOG CALL + INTENT
        # ---------------------------------------------------------
        
        recording_url = message.get("recordingUrl") or message.get("stereoRecordingUrl") or ""
        summary = message.get("analysis", {}).get("summary") or "No summary available."
        
        # Simple Intent Classification
        intent = "General Inquiry"
        lower_trans = transcript.lower()
        if extracted.get("guest_name"):
            intent = "New Reservation"
        elif "cancel" in lower_trans:
            intent = "Cancellation"
        elif "change" in lower_trans or "reschedule" in lower_trans:
            intent = "Modification"
        elif "menu" in lower_trans or "food" in lower_trans:
            intent = "Menu Inquiry"
        elif "hours" in lower_trans or "open" in lower_trans:
            intent = "Hours Inquiry"

        # Log to Airtable
        if restaurant_id and airtable:
            airtable.log_call({
                "restaurant_id": restaurant_id,
                "call_id": message.get("call", {}).get("id") or "unknown",
                "caller_number": dialed_number,
                "intent": intent,
                "outcome": "completed",
                "agent_summary": summary,
                "recording_url": recording_url,
                "transcript": transcript,
                "timestamp": datetime.now().isoformat()
            })
            logger.info("✅ Call log saved to Airtable")

        logger.info("💾 Reservation saved from transcript")
        return {}

    # ---------------------------------------------------------
    # TOOL CALLS — (still allowed, but unused now)
    # ---------------------------------------------------------
    if msg_type in ["response.function_call_arguments", "response.create"]:
        return await handle_tool_call(payload)

    # ---------------------------------------------------------
    # ASSISTANT REQUEST (initial call routing)
    # ---------------------------------------------------------
    if msg_type == "assistant-request":
        dialed_number = extract_dialed_number(message)
        logger.info(f"📞 Extracted dialed number: {dialed_number}")

        record, name, system_prompt = resolve_restaurant_and_prompt(dialed_number)

        if not record:
            logger.warning("⚠️ No restaurant found for this number")
            return {
                "assistant": {
                    "firstMessage": "Sorry, I cannot identify this business right now.",
                    "model": {"provider": "openai", "model": "gpt-3.5-turbo"},
                }
            }

        required_fields = ["guest_name", "date", "guest_phone", "guests"]

        logger.info(f"✅ Routing call to: {name}")

        return {
            "assistant": {
                "firstMessage": f"Hi, thanks for calling {name}. How can I help you?",
                "voice": {"provider": "vapi", "voiceId": "Paige"},
                "model": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.5,
                    "systemPrompt": system_prompt,
                },
                "transcriber": {
                    "provider": "deepgram",
                    "model": "nova-2",
                    "language": "en-US"
                },
            },
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "create_reservation",
                        "description": "Save a reservation to the pending queue.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "guest_name": {"type": "string"},
                                "guest_phone": {"type": "string"},
                                "date": {"type": "string"},
                                "time": {"type": "string"},
                                "guests": {"type": "integer"},
                                "special_requests": {"type": "string"},
                            },
                            "required": required_fields,
                        },
                    },
                }
            ],
            "toolChoice": "auto",
            "turnDetection": {
                "type": "serverVad",
                "threshold": 0.8,
                "prefixPaddingMs": 300,
                "silenceDurationMs": 1000
            },
        }

    logger.info(f"ℹ️ Ignoring message type: {msg_type}")
    return {
        "status": "ok"
    }


# ---------------------------------------------------------
# TOOL CALL HANDLER (unchanged)
# ---------------------------------------------------------
async def handle_tool_call(payload: dict):
    try:
        message = payload.get("message", {}) or {}
        response = message.get("response", {}) or {}

        outputs = response.get("output", []) or []
        tool_calls = []

        for chunk in outputs:
            if "tool_calls" in chunk:
                tool_calls.extend(chunk["tool_calls"])

        logger.info(f"🛠 Extracted tool calls = {len(tool_calls)}")

        if not tool_calls:
            return {"results": []}

        dialed_number = extract_dialed_number(message)
        restaurant_id = None

        if dialed_number:
            record = airtable.get_restaurant_by_phone(dialed_number)
            if record:
                restaurant_id = record.get("id")
                logger.info(f"🔗 Reservation linked to restaurant {restaurant_id}")

        results = []

        for tc in tool_calls:
            call_id = tc.get("id")
            raw_args = tc.get("arguments") or "{}"

            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except:
                    args = {}
            else:
                args = raw_args

            logger.info(f"📦 Tool args parsed: {args}")

            add_pending_reservation({
                "restaurant_id": restaurant_id,
                "guest_name": args.get("guest_name", ""),
                "guest_phone": args.get("guest_phone", ""),
                "date": args.get("date", ""),
                "time": args.get("time", ""),
                "guests": args.get("guests", 2),
                "special_requests": args.get("special_requests", "")
            })

            results.append({
                "toolCallId": call_id,
                "result": "Reservation queued successfully"
            })

        return {"results": results}

    except Exception:
        logger.exception("❌ Tool handler crashed")
        return {"results": []}

class SignupPayload(BaseModel):
    business_name: str
    full_name: str
    occupation: str
    email: str
    phone: str


try:
    users_airtable = UsersAirtable()
    logger.info("✅ Users Airtable ready")
except Exception as e:
    logger.error(f"❌ Users Airtable init failed: {e}")
    users_airtable = None


@app.post("/signup")
def signup_user(payload: SignupPayload):
    if not users_airtable:
        raise HTTPException(status_code=500, detail="Users DB unavailable")

    try:
        data = payload.dict()
        data["email"] = data["email"].lower().strip()
        users_airtable.create_user(data)
        return {"status": "ok"}
    except Exception as e:
        logger.exception("❌ Signup failed")
        raise HTTPException(status_code=500, detail="Signup failed")

class OTPRequest(BaseModel):
    email: str


@app.post("/auth/request-otp")
def request_otp(payload: OTPRequest):
    email = payload.email.lower().strip()

    # ✅ CHECK IF USER EXISTS
    if not users_airtable.user_exists_by_email(email):
        raise HTTPException(
            status_code=404,
            detail="User not registered"
        )

    otp = f"{random.randint(1000, 9999)}"
    expires_at = time.time() + OTP_EXPIRY_SECONDS

    OTP_STORE[email] = {
        "otp": otp,
        "expires_at": expires_at
    }

    try:
        send_otp_email(email, otp)
        return {"status": "otp_sent"}
    except Exception as e:
        logger.exception("OTP email failed")
        raise HTTPException(status_code=500, detail="Failed to send OTP")

class OTPVerify(BaseModel):
    email: str
    otp: str


@app.post("/auth/verify-otp")
def verify_otp(payload: OTPVerify):
    email = payload.email.lower().strip()
    otp = payload.otp.strip()

    record = OTP_STORE.get(email)

    if not record:
        raise HTTPException(status_code=400, detail="OTP not found")

    if time.time() > record["expires_at"]:
        del OTP_STORE[email]
        raise HTTPException(status_code=400, detail="OTP expired")

    if record["otp"] != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    del OTP_STORE[email]

    # 🔹 FETCH USER
    user = users_airtable.get_user_by_email(email)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    fields = user["fields"]

    if fields.get("status") != "done":
        raise HTTPException(
            status_code=403,
            detail="Account not activated yet"
        )

    restaurant_id = fields.get("restaurant_id")

    if not restaurant_id:
        raise HTTPException(
            status_code=403,
            detail="Restaurant not linked yet"
        )

    # 🔒 CRITICAL: verify restaurant exists
    restaurant = airtable.get_restaurant_by_id(str(restaurant_id))
    if not restaurant:
        raise HTTPException(
            status_code=403,
            detail="Invalid restaurant_id"
        )

    return {
        "status": "verified",
        "email": email,
        "restaurant_id": restaurant_id
    }

@app.get("/dashboard/call-logs/{restaurant_id}")
def get_call_logs_for_dashboard(restaurant_id: str):
    if not airtable:
        raise HTTPException(status_code=500, detail="Airtable not available")

    # 🔒 Ensure restaurant actually exists
    restaurant = airtable.get_restaurant_by_id(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    logs = airtable.get_call_logs_by_restaurant(restaurant_id)

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
    records = airtable.get_call_logs_by_restaurant(restaurant_id)

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
