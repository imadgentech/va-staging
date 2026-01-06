import os
import json
import logging
import hashlib
from datetime import datetime
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jose import jwt

from backend.core.users_airtable import UsersAirtable
from backend.core.airtable_client import AirtableManager
from backend.core.prompts import build_system_prompt
from backend.core.reservation_mapper import router as reservation_mapper_router
from backend.core.pending_saver import add_pending_reservation
from backend.core.extract_from_transcript import extract_reservation_from_transcript

# ---------------------------------------------------------
# ENV + LOGGING
# ---------------------------------------------------------
load_dotenv(override=True)

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ALGO = "HS256"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Server")

# ---------------------------------------------------------
# APP INIT
# ---------------------------------------------------------
app = FastAPI(title="Voice Orchestrator")
app.include_router(reservation_mapper_router, prefix="")

# CORS: keep permissive for now; later lock to your Vercel domain(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# CLIENTS INIT
# ---------------------------------------------------------
try:
    airtable = AirtableManager()
    logger.info("✅ Airtable connection established")
except Exception as e:
    logger.error(f"❌ Airtable init failed: {e}")
    airtable = None

try:
    users_airtable = UsersAirtable()
    logger.info("✅ Users Airtable ready")
except Exception as e:
    logger.error(f"❌ Users Airtable init failed: {e}")
    users_airtable = None


# ---------------------------------------------------------
# AUTH HELPERS (PASSWORD)
# ---------------------------------------------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_access_token(data: dict) -> str:
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGO)


# ---------------------------------------------------------
# VAPI HELPERS
# ---------------------------------------------------------
def extract_dialed_number(message: dict) -> str:
    """
    Try multiple possible Vapi shapes to extract the CALLED business number.
    """
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


def _save_last_vapi_payload(payload: dict):
    try:
        with open("last_vapi_request.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------
# HEALTH
# ---------------------------------------------------------
@app.get("/")
def health_check():
    return {"status": "online", "service": "Voice Orchestrator"}


@app.get("/inbound")
def inbound_health():
    return {"status": "ready", "message": "POST Vapi call events here"}


# ---------------------------------------------------------
# VAPI WEBHOOK (MAIN)
# ---------------------------------------------------------
@app.post("/inbound")
async def vapi_webhook(request: Request):
    payload = await request.json()
    _save_last_vapi_payload(payload)

    message = payload.get("message", {}) or {}
    msg_type = message.get("type")

    logger.info(f"🔔 Incoming Vapi message type={msg_type}")

    # ---------------------------------------------------------
    # 1) END OF CALL REPORT: extract from transcript -> queue
    # ---------------------------------------------------------
    if msg_type == "end-of-call-report":
        if not airtable:
            logger.warning("⚠️ Airtable not initialized; cannot resolve restaurant")
            return {"ok": False}

        transcript = message.get("transcript", "") or ""
        if not transcript.strip():
            logger.warning("⚠️ end-of-call-report has no transcript")
            return {"ok": True}

        dialed_number = extract_dialed_number(message)

        restaurant_record_id = None        # recXXXX (Airtable record id)
        restaurant_business_id = None      # 3 (Autonumber field inside Restaurants)

        if dialed_number:
            rec = airtable.get_restaurant_by_phone(dialed_number)
            if rec:
                restaurant_record_id = rec.get("id")
                restaurant_business_id = (rec.get("fields", {}) or {}).get("restaurant_id")

        # IMPORTANT:
        # Keep restaurant_id as recXXXX because your PendingReservations uses recXXXX
        extracted = extract_reservation_from_transcript(transcript, restaurant_record_id)

        # Optional: also store business id for dashboard / logs
        extracted["restaurant_business_id"] = restaurant_business_id


        if not extracted:
            logger.info("ℹ️ No reservation extracted from transcript")
            return {"ok": True}

        logger.info(f"📌 Extracted reservation from transcript: {extracted}")

        success = add_pending_reservation(extracted)
        logger.info(f"📥 add_pending_reservation success={success}")

        # ---------------------------------------------------------
        # LOG CALL TO AIRTABLE
        # ---------------------------------------------------------
        try:
            call_info = message.get("call", {}) or {}
            analysis = message.get("analysis", {}) or {}
            
            # Helper to safely stringify
            def safe_str(v): return str(v) if v is not None else ""

            log_payload = {
                "call_id": call_info.get("id"),
                "restaurant_id": str(restaurant_business_id) if restaurant_business_id else None,
                "restaurant_number": dialed_number,
                "caller_number": call_info.get("customer", {}).get("number"),
                "timestamp": message.get("timestamp") or datetime.now().isoformat(),
                "outcome": message.get("endedReason"),
                "recording_url": message.get("recordingUrl"),
                "agent_summary": analysis.get("summary"),
                "transcript": transcript,
                "cost": message.get("cost"),
                "intent": "Reservation" if extracted else "General Inquiry"
            }
            
            # Remove None values to avoid Airtable errors if columns missing? 
            # Actually pyairtable usually handles it, but safer to omit None if not sure.
            # But let's keep it simple.
            
            logger.info(f"📝 Logging call: {log_payload.get('call_id')}")
            airtable.log_call(log_payload)
            
        except Exception as e:
            logger.error(f"❌ Failed to log call: {e}")

        return {"ok": True}

    # ---------------------------------------------------------
    # 2) TOOL CALLS (optional fallback if Vapi triggers tools)
    # ---------------------------------------------------------
    # Many Vapi payloads use msg_type == "tool-calls"
    if msg_type in ["tool-calls", "tool_call", "toolcall"]:
        return await handle_tool_calls(message)

    # ---------------------------------------------------------
    # 3) ASSISTANT REQUEST (call start) -> return dynamic assistant config
    # ---------------------------------------------------------
    if msg_type == "assistant-request":
        if not airtable:
            return {
                "assistant": {
                    "firstMessage": "Sorry, the system is not ready yet.",
                    "model": {"provider": "openai", "model": "gpt-3.5-turbo"},
                }
            }

        dialed_number = extract_dialed_number(message)
        logger.info(f"📞 Dialed number: {dialed_number}")

        record, name, system_prompt = resolve_restaurant_and_prompt(dialed_number)

        if not record:
            return {
                "assistant": {
                    "firstMessage": "Sorry, I cannot identify this business right now.",
                    "model": {"provider": "openai", "model": "gpt-3.5-turbo"},
                }
            }

        required_fields = ["guest_name", "date", "guest_phone", "guests"]

        # IMPORTANT:
        # Tools must be inside assistant.model.tools for Vapi to attach them correctly.
        return {
            "assistant": {
                "firstMessage": f"Hi, thanks for calling {name}. How can I help you?",
                "voice": {"provider": "vapi", "voiceId": "Paige"},
                "model": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.5,
                    "systemPrompt": system_prompt,
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "create_reservation",
                                "description": "Queue a reservation payload to be saved by background saver.",
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
                },
            },
            "turnDetection": {"type": "serverVad"},
        }

    # ---------------------------------------------------------
    # Unknown event types: ignore safely
    # ---------------------------------------------------------
    logger.info(f"ℹ️ Ignoring msg_type={msg_type}")
    return {"ok": True}


# ---------------------------------------------------------
# TOOL CALL HANDLER (robust parsing)
# ---------------------------------------------------------
async def handle_tool_calls(message: dict):
    """
    Supports multiple shapes:
    - message.toolCallList: [{id,name,parameters}]
    - message.toolCalls:    [{id,function:{name,arguments}}]
    """
    try:
        if not airtable:
            logger.warning("⚠️ Airtable not initialized; tool call will still queue without restaurant")
        tool_calls = message.get("toolCallList") or message.get("toolCalls") or []
        if not isinstance(tool_calls, list):
            tool_calls = []

        logger.info(f"🛠 Received tool calls: {len(tool_calls)}")

        dialed_number = extract_dialed_number(message)
        restaurant_id = None

        if dialed_number and airtable:
            rec = airtable.get_restaurant_by_phone(dialed_number)
            restaurant_id = rec.get("id") if rec else None

        results = []

        for tool in tool_calls:
            call_id = tool.get("id")

            # shape A: { id, name, parameters }
            tool_name = tool.get("name")
            args = tool.get("parameters")

            # shape B: { id, function: { name, arguments } }
            fn = tool.get("function") or {}
            if not tool_name:
                tool_name = fn.get("name")
            if args is None:
                args = fn.get("arguments")

            # normalize args: string -> dict
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}

            logger.info(f"📦 Tool={tool_name} args={args}")

            # queue it
            queued = add_pending_reservation(
                {
                    "restaurant_id": restaurant_id,
                    "guest_name": args.get("guest_name", ""),
                    "guest_phone": args.get("guest_phone", ""),
                    "date": args.get("date", ""),
                    "time": args.get("time", ""),
                    "guests": args.get("guests", 2),
                    "special_requests": args.get("special_requests", ""),
                }
            )

            results.append(
                {
                    "toolCallId": call_id,
                    "result": "Reservation queued successfully." if queued else "Failed to queue reservation.",
                }
            )

        return {"results": results}

    except Exception:
        logger.exception("❌ Tool handler error")
        return {"results": []}


# ---------------------------------------------------------
# SIGNUP + LOGIN (PASSWORD)
# ---------------------------------------------------------
class SignupPayload(BaseModel):
    business_name: str
    full_name: str
    occupation: str
    email: str
    phone: str
    password: str


@app.post("/signup")
def signup_user(payload: SignupPayload):
    if not users_airtable:
        raise HTTPException(status_code=500, detail="Users DB unavailable")

    try:
        data = payload.dict()
        data["email"] = data["email"].lower().strip()

        raw_password = data.pop("password")
        data["password"] = hash_password(raw_password)

        users_airtable.create_user(data)
        return {"status": "ok"}
    except Exception:
        logger.exception("❌ Signup failed")
        raise HTTPException(status_code=500, detail="Signup failed")


class LoginPayload(BaseModel):
    email: str
    password: str


@app.post("/auth/login")
def login(payload: LoginPayload):
    if not users_airtable:
        raise HTTPException(status_code=500, detail="Users DB unavailable")

    email = payload.email.lower().strip()
    password = payload.password.strip()

    user = users_airtable.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    fields = user.get("fields", {}) or {}
    stored_hash = fields.get("password", "")

    if hash_password(password) != stored_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    status = fields.get("status", "pending")
    restaurant_id = fields.get("restaurant_id")

    return {
        "status": "success",
        "email": email,
        "user_status": status,
        "restaurant_id": restaurant_id,
        # "token": create_access_token({"sub": email})  # optional
    }


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
@app.get("/dashboard/call-logs/{restaurant_id}")
def get_call_logs_for_dashboard(restaurant_id: str):
    if not airtable:
        raise HTTPException(status_code=500, detail="Airtable not available")

    restaurant = airtable.get_restaurant_by_id(restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    logs = airtable.get_call_logs_by_restaurant(restaurant_id)

    return {
        "restaurant_id": restaurant_id,
        "count": len(logs),
        "logs": [
            {
                "call_id": r.get("fields", {}).get("call_id"),
                "intent": r.get("fields", {}).get("intent"),
                "outcome": r.get("fields", {}).get("outcome"),
                "agent_summary": r.get("fields", {}).get("agent_summary"),
                "recording_url": r.get("fields", {}).get("recording_url"),
                "timestamp": r.get("fields", {}).get("timestamp"),
            }
            for r in logs
        ],
    }


@app.get("/dashboard/stats/{restaurant_id}")
def get_dashboard_stats(restaurant_id: str):
    if not airtable:
        raise HTTPException(status_code=500, detail="Airtable not available")

    records = airtable.get_call_logs_by_restaurant(restaurant_id)
    total_calls = len(records)

    missed_calls = sum(
        1 for r in records
        if (r.get("fields", {}) or {}).get("outcome") == "missed"
    )

    hourly = {}
    for r in records:
        fields = r.get("fields", {}) or {}
        ts = fields.get("created_at") or fields.get("timestamp")
        if not ts or not isinstance(ts, str) or len(ts) < 13:
            continue
        hour = ts[11:13]
        hourly[hour] = hourly.get(hour, 0) + 1

    by_hour = [{"hour": h, "calls": c} for h, c in sorted(hourly.items())]

    intent_map = {}
    for r in records:
        fields = r.get("fields", {}) or {}
        intent = fields.get("intent", "Unknown")
        intent_map[intent] = intent_map.get(intent, 0) + 1

    intent_breakdown = [{"intent": k, "count": v} for k, v in intent_map.items()]

    return {
        "total_calls": total_calls,
        "missed_calls": missed_calls,
        "by_hour": by_hour,
        "intent_breakdown": intent_breakdown,
    }
