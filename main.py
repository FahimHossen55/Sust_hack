import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

load_dotenv()

from analyzer import analyze_ticket
from llm_analyzer import call_groq
from models import TicketRequest
from safety import audit_response, is_prompt_injection

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="QueueStorm Investigator",
    description="AI/API support copilot for digital finance ticket triage.",
    version="1.0.0",
)


# Return 400 (not FastAPI default 422) for missing/invalid fields
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": "Missing or invalid required fields.", "details": str(exc.errors())},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze-ticket", response_model=None)
async def analyze(ticket: TicketRequest):
    # --- Semantic validation ---
    if not ticket.complaint or not ticket.complaint.strip():
        return JSONResponse(
            status_code=422,
            content={"error": "Complaint field cannot be empty."},
        )

    # --- Prompt injection guard ---
    if is_prompt_injection(ticket.complaint):
        logger.warning("Prompt injection detected in ticket %s", ticket.ticket_id)

    # Convert to dict for Groq (serializes nested models too)
    body = ticket.model_dump()

    # --- Analysis: Groq LLM -> rule-based fallback ---
    result = None
    try:
        result = call_groq(body)
    except Exception as exc:
        logger.error("Groq error for ticket %s: %s", ticket.ticket_id, exc)

    if result is None:
        logger.info("Rule-based fallback for ticket %s", ticket.ticket_id)
        try:
            result = analyze_ticket(ticket)
        except Exception as exc:
            logger.error("Rule-based failed for ticket %s: %s", ticket.ticket_id, exc)
            return JSONResponse(
                status_code=500,
                content={"error": "Internal server error. Please try again."},
            )

    # --- Safety audit ---
    violations = audit_response(result["customer_reply"], result["recommended_next_action"])
    if violations:
        logger.warning("Safety violations in ticket %s: %s", ticket.ticket_id, violations)

    logger.info(
        "Ticket %s -> case=%s severity=%s verdict=%s human_review=%s",
        ticket.ticket_id,
        result["case_type"],
        result["severity"],
        result["evidence_verdict"],
        result["human_review_required"],
    )

    return JSONResponse(status_code=200, content=result)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
