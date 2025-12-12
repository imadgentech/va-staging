import logging
import json
from datetime import datetime
from fastapi import FastAPI, Request
from dotenv import load_dotenv

from src.core.airtable_client import AirtableManager
from src.core.prompts import build_system_prompt
from src.core.reservation_mapper import router as reservation_mapper_router
from src.core.pending_saver import add_pending_reservation
from src.core.extract_from_transcript import extract_reservation_from_transcript

load_dotenv()

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

        # Save to pending queue
        add_pending_reservation(extracted)

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
            "turnDetection": {"type": "serverVad"},
        }

    logger.info(f"ℹ️ Ignoring message type: {msg_type}")
    return {}


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
