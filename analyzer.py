import re
from typing import Optional, List, Tuple
from models import TicketRequest, TransactionEntry

# ---------------------------------------------------------------------------
# Keyword sets for each case type (English + Bangla + Banglish)
# ---------------------------------------------------------------------------
CASE_KEYWORDS: dict[str, list[str]] = {
    "wrong_transfer": [
        "wrong number", "wrong person", "wrong recipient", "wrong account",
        "wrong mobile", "sent to wrong", "mistakenly sent", "wrong transfer",
        "ভুল নম্বর", "ভুল", "bhul number", "bhul", "wrong bkash",
        "accidentally sent", "sent by mistake", "unintended", "wrong no",
        "wrong num", "send to wrong", "transferred to wrong",
    ],
    "payment_failed": [
        "failed", "not received", "deducted but", "balance cut",
        "transaction failed", "unsuccessful", "ব্যর্থ", "কাটা গেছে",
        "payment failed", "money deducted", "charged but not", "not credited",
        "balance deducted", "amount deducted", "money gone but",
        "cut but not", "fail hoise", "fail hoiche", "not showing",
        "deducted not", "deducted however",
    ],
    "refund_request": [
        "refund", "money back", "return my money", "ফেরত", "ফেরত দিন",
        "want back", "get back my money", "return the amount", "reimburse",
        "pay back", "give back", "give me back", "return money",
        "refund korte", "refund chai",
    ],
    "duplicate_payment": [
        "twice", "double", "duplicate", "charged twice", "2 times", "two times",
        "deducted twice", "double deduction", "paid twice", "same payment twice",
        "multiple times", "again deducted", "twice deducted", "double charge",
        "deducted 2 times", "deducted two times",
    ],
    "merchant_settlement_delay": [
        "settlement", "merchant", "not received payment from",
        "payment not settled", "merchant account", "shop", "store",
        "business payment", "merchant payment", "settlement delay",
        "not getting payment", "payment not coming", "merchant side",
    ],
    "agent_cash_in_issue": [
        "cash in", "agent", "deposit", "add money", "not reflected",
        "not added", "cash deposit", "agent point", "cash-in", "cashin",
        "নগদ জমা", "এজেন্ট", "balance not updated", "deposited but",
        "cash in korechi", "cash in dilam", "agent e diyechi",
    ],
    "phishing_or_social_engineering": [
        "otp", "pin", "password", "someone called", "fake call", "hacked",
        "fraud call", "scam", "someone asked", "share otp", "ওটিপি", "পিন",
        "suspicious", "unknown caller", "asked for otp", "asked my pin",
        "account hacked", "unauthorized", "fake agent", "impersonator",
        "share pin", "share password", "asked pin", "asked otp",
        "give otp", "give pin", "told me to share",
    ],
}

AMOUNT_RE = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s*(?:taka|tk|bdt|৳)?\b", re.IGNORECASE)


def _extract_amounts(text: str) -> List[float]:
    results = []
    for m in AMOUNT_RE.findall(text):
        try:
            results.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return results


def classify_case_type(complaint: str) -> Tuple[str, float, List[str]]:
    """Return (case_type, confidence, reason_codes)."""
    lower = complaint.lower()
    scores: dict[str, Tuple[int, List[str]]] = {}

    for case_type, keywords in CASE_KEYWORDS.items():
        hits = [kw for kw in keywords if kw.lower() in lower]
        scores[case_type] = (len(hits), hits)

    best_type = "other"
    best_score = 0
    best_hits: List[str] = []

    for ct, (score, hits) in scores.items():
        if score > best_score:
            best_score = score
            best_type = ct
            best_hits = hits

    confidence = round(min(0.92, 0.50 + best_score * 0.12), 2) if best_score else 0.40
    reason_codes = [best_type] + [h.replace(" ", "_") for h in best_hits[:2]]
    return best_type, confidence, reason_codes


def find_relevant_transaction(
    complaint: str, transactions: List[TransactionEntry]
) -> Optional[TransactionEntry]:
    if not transactions:
        return None

    lower = complaint.lower()
    amounts_in_complaint = _extract_amounts(complaint)

    best_tx: Optional[TransactionEntry] = None
    best_score = 0

    for tx in transactions:
        score = 0

        # Exact transaction ID mentioned
        if tx.transaction_id and tx.transaction_id.lower() in lower:
            score += 5

        # Amount match
        if tx.amount and amounts_in_complaint:
            if any(abs(tx.amount - a) < 0.01 for a in amounts_in_complaint):
                score += 3

        # Counterparty mentioned
        if tx.counterparty and tx.counterparty in complaint:
            score += 2

        # Transaction type keyword match
        type_kw_map = {
            "transfer": ["transfer", "sent", "send", "পাঠিয়েছি", "pathiyechi"],
            "payment": ["payment", "paid", "pay", "merchant", "shop"],
            "cash_in": ["cash in", "deposit", "add money", "cashin"],
            "cash_out": ["cash out", "withdraw", "taka tulte"],
            "settlement": ["settlement"],
            "refund": ["refund"],
        }
        if tx.type:
            for kws in type_kw_map.get(tx.type, []):
                if kws in lower:
                    score += 1

        if score > best_score:
            best_score = score
            best_tx = tx

    return best_tx if best_score > 0 else None


def determine_evidence_verdict(
    complaint: str, tx: Optional[TransactionEntry], case_type: str
) -> str:
    if not tx:
        return "insufficient_data"

    lower = complaint.lower()

    # Failed complaint but completed transaction → inconsistent
    if case_type == "payment_failed" and tx.status == "completed":
        return "inconsistent"

    # Failed complaint and failed/pending transaction → consistent
    if case_type == "payment_failed" and tx.status in ("failed", "pending"):
        return "consistent"

    # Wrong transfer with completed transfer → consistent
    if case_type == "wrong_transfer" and tx.type == "transfer" and tx.status == "completed":
        return "consistent"

    # Refund request but already reversed → inconsistent
    if case_type == "refund_request" and tx.status == "reversed":
        return "inconsistent"

    # Duplicate payment needs more data than one transaction
    if case_type == "duplicate_payment":
        return "insufficient_data"

    # Amount in complaint matches transaction amount → consistent
    amounts = _extract_amounts(complaint)
    if amounts and tx.amount and any(abs(tx.amount - a) < 0.01 for a in amounts):
        return "consistent"

    return "insufficient_data"


def determine_severity(
    case_type: str, tx: Optional[TransactionEntry], complaint: str
) -> str:
    if case_type == "phishing_or_social_engineering":
        return "critical"

    amount = tx.amount if tx else None
    if amount is None:
        amounts = _extract_amounts(complaint)
        amount = max(amounts) if amounts else 0.0

    if case_type in ("wrong_transfer", "payment_failed"):
        if amount >= 10000:
            return "critical"
        if amount >= 5000:
            return "high"
        return "medium"

    if case_type == "duplicate_payment":
        return "high"

    if case_type in ("merchant_settlement_delay", "agent_cash_in_issue"):
        return "medium"

    if case_type == "refund_request":
        return "low"

    return "low"


def determine_department(case_type: str) -> str:
    mapping = {
        "wrong_transfer": "dispute_resolution",
        "payment_failed": "payments_ops",
        "refund_request": "dispute_resolution",
        "duplicate_payment": "payments_ops",
        "merchant_settlement_delay": "merchant_operations",
        "agent_cash_in_issue": "agent_operations",
        "phishing_or_social_engineering": "fraud_risk",
        "other": "customer_support",
    }
    return mapping.get(case_type, "customer_support")


def should_require_human_review(
    case_type: str, severity: str, evidence_verdict: str
) -> bool:
    if severity in ("high", "critical"):
        return True
    if case_type in ("wrong_transfer", "phishing_or_social_engineering", "duplicate_payment"):
        return True
    if evidence_verdict == "inconsistent":
        return True
    return False


# ---------------------------------------------------------------------------
# Text generation helpers
# ---------------------------------------------------------------------------

def _fmt(template: str, tx_id: str, amount: str, status: str) -> str:
    return template.format(tx_id=tx_id, amount=amount, status=status)


AGENT_SUMMARY_TEMPLATES = {
    "wrong_transfer": (
        "Customer reports sending {amount}BDT to the wrong recipient"
        "{tx_part}. Transaction status: {status}."
    ),
    "payment_failed": (
        "Customer reports a {amount}BDT transaction{tx_part} that failed "
        "or where balance was deducted without confirmation."
    ),
    "refund_request": (
        "Customer is requesting a refund for {amount}BDT{tx_part}."
    ),
    "duplicate_payment": (
        "Customer reports being charged twice for the same payment of {amount}BDT{tx_part}."
    ),
    "merchant_settlement_delay": (
        "Merchant or customer reports a delayed settlement of {amount}BDT{tx_part}."
    ),
    "agent_cash_in_issue": (
        "Customer reports a cash-in of {amount}BDT through an agent{tx_part} "
        "that was not reflected in their balance."
    ),
    "phishing_or_social_engineering": (
        "Customer may have been targeted by a phishing or social engineering attack. "
        "Immediate security review required."
    ),
    "other": "Customer has submitted a complaint that requires agent review.",
}

NEXT_ACTION_TEMPLATES = {
    "wrong_transfer": (
        "Verify transaction{tx_part} details. Check sender and receiver accounts. "
        "Escalate to dispute resolution team to initiate the recall process per policy."
    ),
    "payment_failed": (
        "Check transaction{tx_part} status in payment logs. Verify if balance was deducted. "
        "Escalate to payments operations team for investigation."
    ),
    "refund_request": (
        "Review transaction{tx_part} eligibility for refund per policy. "
        "Escalate to dispute resolution team if applicable."
    ),
    "duplicate_payment": (
        "Check transaction logs for duplicate entries near the same timestamp and amount. "
        "Cross-reference{tx_part} and escalate to payments operations."
    ),
    "merchant_settlement_delay": (
        "Check settlement batch status for the merchant account{tx_part}. "
        "Verify payment processing timeline with merchant operations."
    ),
    "agent_cash_in_issue": (
        "Verify cash-in transaction{tx_part} with the agent ID. "
        "Confirm if the cash-in was processed on the agent side and escalate to agent operations."
    ),
    "phishing_or_social_engineering": (
        "Immediately flag the account for security review. "
        "Check for unauthorized transactions and alert the fraud risk team."
    ),
    "other": (
        "Review complaint details carefully and route to the appropriate team for resolution."
    ),
}

CUSTOMER_REPLY_TEMPLATES = {
    "wrong_transfer": (
        "Thank you for contacting us. We have received your report{tx_part}. "
        "Our team will investigate this matter thoroughly. "
        "If any resolution is available, it will be processed through official channels. "
        "Please do not share your PIN, OTP, or password with anyone. "
        "We will keep you updated on the outcome."
    ),
    "payment_failed": (
        "Thank you for reaching out. We have noted your concern{tx_part}. "
        "Our team is looking into this matter. "
        "If any amount was incorrectly deducted, any eligible adjustment will be made "
        "through official channels. We will follow up with you shortly."
    ),
    "refund_request": (
        "Thank you for contacting us. We have received your request{tx_part}. "
        "Our team will review the transaction details. "
        "If eligible, any amount owed will be returned through official channels as per our policy. "
        "We will update you on the status."
    ),
    "duplicate_payment": (
        "Thank you for reporting this issue{tx_part}. "
        "Our team will investigate the transaction records for any duplicate charges. "
        "If a duplicate payment is confirmed, any eligible amount will be returned "
        "through official channels."
    ),
    "merchant_settlement_delay": (
        "Thank you for contacting us. We have noted your concern about the settlement delay{tx_part}. "
        "Our merchant operations team will review the account and investigate. "
        "We will provide you with an update shortly."
    ),
    "agent_cash_in_issue": (
        "Thank you for reaching out. We have received your report about the cash-in{tx_part}. "
        "Our agent operations team will verify the transaction with the agent. "
        "If the amount was received but not credited, it will be resolved through official channels."
    ),
    "phishing_or_social_engineering": (
        "Thank you for alerting us. "
        "Please do not share your PIN, OTP, password, or any personal information with anyone, "
        "including anyone claiming to be from our support team — "
        "our official staff will never ask for these details. "
        "Your account has been flagged for a security review. "
        "Please contact our official helpline if you notice any unauthorized activity."
    ),
    "other": (
        "Thank you for contacting us. We have received your complaint and our team will review it. "
        "We will get back to you with an update shortly. "
        "Please use only official support channels for follow-up."
    ),
}


def _build_texts(
    case_type: str,
    tx: Optional[TransactionEntry],
    complaint: str,
) -> Tuple[str, str, str]:
    tx_id = tx.transaction_id if tx else None
    amount_val = tx.amount if tx else None
    if amount_val is None:
        amounts = _extract_amounts(complaint)
        amount_val = max(amounts) if amounts else None

    amount_str = f"{int(amount_val)} " if amount_val else ""
    status_str = tx.status if tx else "unknown"
    tx_part = f" regarding transaction {tx_id}" if tx_id else ""
    tx_part_short = f" {tx_id}" if tx_id else ""

    summary_tpl = AGENT_SUMMARY_TEMPLATES.get(case_type, AGENT_SUMMARY_TEMPLATES["other"])
    if case_type in ("phishing_or_social_engineering", "other"):
        agent_summary = summary_tpl
    else:
        agent_summary = summary_tpl.format(
            amount=amount_str, tx_part=tx_part_short, status=status_str
        )

    action_tpl = NEXT_ACTION_TEMPLATES.get(case_type, NEXT_ACTION_TEMPLATES["other"])
    if case_type in ("phishing_or_social_engineering", "other"):
        next_action = action_tpl
    else:
        next_action = action_tpl.format(tx_part=tx_part_short)

    reply_tpl = CUSTOMER_REPLY_TEMPLATES.get(case_type, CUSTOMER_REPLY_TEMPLATES["other"])
    if case_type in ("phishing_or_social_engineering", "other"):
        customer_reply = reply_tpl
    else:
        customer_reply = reply_tpl.format(tx_part=tx_part)

    return agent_summary, next_action, customer_reply


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_ticket(request: TicketRequest) -> dict:
    complaint = request.complaint or ""
    transactions = request.transaction_history or []

    case_type, confidence, reason_codes = classify_case_type(complaint)
    relevant_tx = find_relevant_transaction(complaint, transactions)
    relevant_tx_id = relevant_tx.transaction_id if relevant_tx else None
    evidence_verdict = determine_evidence_verdict(complaint, relevant_tx, case_type)
    severity = determine_severity(case_type, relevant_tx, complaint)
    department = determine_department(case_type)
    human_review = should_require_human_review(case_type, severity, evidence_verdict)

    agent_summary, next_action, customer_reply = _build_texts(
        case_type, relevant_tx, complaint
    )

    if relevant_tx_id and "transaction_match" not in reason_codes:
        reason_codes.append("transaction_match")

    return {
        "ticket_id": request.ticket_id,
        "relevant_transaction_id": relevant_tx_id,
        "evidence_verdict": evidence_verdict,
        "case_type": case_type,
        "severity": severity,
        "department": department,
        "agent_summary": agent_summary,
        "recommended_next_action": next_action,
        "customer_reply": customer_reply,
        "human_review_required": human_review,
        "confidence": confidence,
        "reason_codes": reason_codes,
    }
