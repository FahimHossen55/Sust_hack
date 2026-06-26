import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from analyzer import analyze_ticket
from models import TicketRequest
from safety import audit_response, is_prompt_injection

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="QueueStorm Investigator",
    description="AI/API support copilot for digital finance ticket triage.",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze-ticket")
async def analyze(request: Request):
    # --- Parse raw body ---
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body. Please send a valid JSON object."},
        )

    # --- Validate schema ---
    try:
        ticket = TicketRequest(**body)
    except ValidationError as exc:
        missing = [e["loc"] for e in exc.errors()]
        return JSONResponse(
            status_code=400,
            content={"error": "Missing or invalid required fields.", "details": str(missing)},
        )

    # --- Semantic validation ---
    if not ticket.complaint or not ticket.complaint.strip():
        return JSONResponse(
            status_code=422,
            content={"error": "Complaint field cannot be empty."},
        )

    # --- Prompt injection guard ---
    if is_prompt_injection(ticket.complaint):
        logger.warning("Prompt injection attempt detected in ticket %s", ticket.ticket_id)
        # Still process the ticket normally — just log the signal
        # The rule-based system is inherently injection-resistant

    # --- Core analysis ---
    try:
        result = analyze_ticket(ticket)
    except Exception as exc:
        logger.error("Analysis error for ticket %s: %s", ticket.ticket_id, exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error. Please try again."},
        )

    # --- Safety audit ---
    violations = audit_response(
        result["customer_reply"], result["recommended_next_action"]
    )
    if violations:
        logger.warning(
            "Safety violations for ticket %s: %s", ticket.ticket_id, violations
        )

    logger.info(
        "Ticket %s → case=%s severity=%s verdict=%s",
        ticket.ticket_id,
        result["case_type"],
        result["severity"],
        result["evidence_verdict"],
    )

    return JSONResponse(status_code=200, content=result)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
