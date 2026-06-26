# QueueStorm Investigator

AI/API support copilot for digital finance ticket triage.
Built for **bKash presents SUST CSE Carnival 2026 — Codex Community Hackathon**.

---

## Live Deployment

| Endpoint | URL |
|---|---|
| Health | `https://queuestorm-investigator-0hqv.onrender.com/health` |
| Analyze Ticket | `https://queuestorm-investigator-0hqv.onrender.com/analyze-ticket` |
| Interactive Docs | `https://queuestorm-investigator-0hqv.onrender.com/docs` |

---

## What It Does

QueueStorm Investigator is an internal AI copilot for support agents of a digital finance platform (like bKash). When a customer submits a complaint, the service:

1. Reads the complaint (English, Bangla, or Banglish)
2. Cross-references it with the customer's recent transaction history
3. Identifies the relevant transaction
4. Determines whether the evidence supports or contradicts the complaint
5. Classifies the case type and routes it to the correct department
6. Drafts a safe, professional reply — never asking for PIN/OTP, never promising unauthorized refunds
7. Flags high-risk or ambiguous cases for human review

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | FastAPI + Uvicorn |
| Schema validation | Pydantic v2 |
| AI — Primary | Groq API (`llama-3.3-70b-versatile`) |
| AI — Fallback model | Groq API (`llama-3.1-8b-instant`) |
| AI — Final fallback | Rule-based keyword engine (no external call) |
| Deployment | Render (free tier) |
| Environment | python-dotenv |

---

## Project Structure

```
queuestorm/
├── main.py           # FastAPI app — routes, error handling, orchestration
├── llm_analyzer.py   # Groq LLM integration with primary + fallback model
├── analyzer.py       # Rule-based fallback — keyword matching, transaction scoring
├── safety.py         # Safety audit — credential/commitment/injection checks
├── models.py         # Pydantic request and response schemas
├── requirements.txt  # Python dependencies
├── Dockerfile        # Docker image definition
├── .env.example      # Environment variable template (no real values)
├── sample_output.json # Sample response from live endpoint
└── README.md
```

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/FahimHossen55/Sust_hack.git
cd Sust_hack
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set environment variables

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

`.env` file:
```
GROQ_API_KEY=your_groq_api_key_here
PORT=8000
```

### 4. Run the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Or:
```bash
python main.py
```

### 5. Test it

```bash
python test_api.py
```

---

## Docker

```bash
docker build -t queuestorm-team .
docker run -p 8000:8000 --env-file .env queuestorm-team
```

---

## API Endpoints

### GET /health

Returns service readiness status.

```bash
curl https://queuestorm-investigator-0hqv.onrender.com/health
```

Response:
```json
{"status": "ok"}
```

---

### POST /analyze-ticket

Analyzes a customer support ticket against transaction history.

#### Request fields

| Field | Type | Required | Description |
|---|---|---|---|
| `ticket_id` | string | Yes | Unique ticket identifier |
| `complaint` | string | Yes | Customer complaint (English/Bangla/Banglish) |
| `language` | string | No | `en`, `bn`, or `mixed` |
| `channel` | string | No | `in_app_chat`, `call_center`, `email`, `merchant_portal`, `field_agent` |
| `user_type` | string | No | `customer`, `merchant`, `agent`, `unknown` |
| `campaign_context` | string | No | Campaign identifier |
| `transaction_history` | array | No | List of recent transactions |
| `metadata` | object | No | Additional context |

#### Transaction history entry fields

| Field | Type | Description |
|---|---|---|
| `transaction_id` | string | Unique transaction ID |
| `timestamp` | string | ISO 8601 timestamp |
| `type` | string | `transfer`, `payment`, `cash_in`, `cash_out`, `settlement`, `refund` |
| `amount` | number | Amount in BDT |
| `counterparty` | string | Recipient phone, merchant ID, or agent ID |
| `status` | string | `completed`, `failed`, `pending`, `reversed` |

#### Sample request

```bash
curl -X POST https://queuestorm-investigator-0hqv.onrender.com/analyze-ticket \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "TKT-001",
    "complaint": "I sent 5000 taka to a wrong number around 2pm today",
    "language": "en",
    "channel": "in_app_chat",
    "user_type": "customer",
    "campaign_context": "boishakh_bonanza_day_1",
    "transaction_history": [
      {
        "transaction_id": "TXN-9101",
        "timestamp": "2026-04-14T14:08:22Z",
        "type": "transfer",
        "amount": 5000,
        "counterparty": "+8801719876543",
        "status": "completed"
      }
    ]
  }'
```

#### Sample response

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer claims to have sent 5000 taka to a wrong number. Transaction history shows a completed transfer of the same amount around 2pm.",
  "recommended_next_action": "Investigate the transaction and gather more information from the customer",
  "customer_reply": "We apologize for the inconvenience. Our team will look into this matter and any eligible amount will be returned through official channels.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "high_amount"]
}
```

#### HTTP response codes

| Code | Meaning |
|---|---|
| 200 | Successful analysis |
| 400 | Invalid JSON or missing required fields |
| 422 | Empty complaint field |
| 500 | Internal server error |

---

## MODELS

### Primary: `llama-3.3-70b-versatile` via Groq API

- **Where it runs:** Groq cloud inference (external API call)
- **Why chosen:** Most capable model on Groq free tier; strong JSON structured output; handles English, Bangla, and Banglish; average response time ~2-3 seconds
- **Cost:** Free tier — no charge for preliminary round usage volume

### Fallback 1: `llama-3.1-8b-instant` via Groq API

- **Where it runs:** Groq cloud inference
- **Why chosen:** Activated when primary model hits rate limit or times out; ~0.5 second response time; sufficient for straightforward cases
- **Cost:** Free tier

### Fallback 2: Rule-based keyword engine (no external call)

- **Where it runs:** Locally within the service process
- **Why chosen:** Zero latency, zero cost, no external dependency — guarantees the service always returns a valid response even if Groq is unavailable
- **How it works:**
  - Weighted keyword sets for all 8 case types (English + Bangla + Banglish)
  - Regex-based BDT amount extraction
  - Scoring system to match complaint to the most relevant transaction
  - Deterministic evidence verdict rules based on transaction status vs complaint intent

---

## AI Approach

The service uses a **three-layer hybrid approach**:

```
Request
  |
  v
[Layer 1] Groq llama-3.3-70b-versatile
  | fails (rate limit / timeout / bad JSON)
  v
[Layer 2] Groq llama-3.1-8b-instant
  | fails
  v
[Layer 3] Rule-based fallback (always succeeds)
  |
  v
[Safety audit] — runs on ALL outputs regardless of layer
  |
  v
Response
```

The LLM is given a structured system prompt that:
- Explains the investigation task
- Lists all valid enum values with exact spellings
- Provides routing and severity guidelines
- Enforces safety rules explicitly
- Requests JSON-only output using `response_format={"type": "json_object"}`

All LLM outputs are validated against the required schema before being returned. Invalid enum values or missing fields cause automatic fallback to the next layer.

---

## Safety Logic

Three hard safety rules are enforced on every response, regardless of which layer produced it:

### Rule 1 — No credential solicitation (penalty: -15 points)
`customer_reply` must never ask for PIN, OTP, password, or card number — not even framed as a verification step.

**How enforced:** The LLM system prompt explicitly prohibits it. `safety.py` runs regex checks on every `customer_reply` before it is returned and logs any violations.

### Rule 2 — No unauthorized financial commitments (penalty: -10 points)
`customer_reply` and `recommended_next_action` must never promise a refund, reversal, or account unblock.

**Safe language used:** "any eligible amount will be returned through official channels"

**How enforced:** LLM prompt includes explicit examples of wrong vs right language. Post-generation regex audit catches any violations.

### Rule 3 — No suspicious third-party referral (penalty: -10 points)
Customers are only directed to official support channels.

**How enforced:** LLM prompt and rule-based templates both avoid any third-party references.

### Prompt injection resistance
The `is_prompt_injection()` function in `safety.py` detects adversarial instructions embedded in complaint text (e.g., "ignore all previous instructions") and logs them. The rule-based fallback is inherently injection-resistant since it uses keyword matching, not an LLM.

---

## Evidence Reasoning

The investigator cross-references the complaint with transaction history using these rules:

| Complaint intent | Transaction status | Evidence verdict |
|---|---|---|
| Payment failed | `completed` | `inconsistent` |
| Payment failed | `failed` or `pending` | `consistent` |
| Wrong transfer | Transfer `completed`, amount matches | `consistent` |
| Refund request | Status is `reversed` | `inconsistent` (already processed) |
| No matching transaction found | — | `insufficient_data` |
| Duplicate payment claim | Single transaction visible | `insufficient_data` |

`relevant_transaction_id` is identified by scoring each transaction against the complaint on: amount match (+3), transaction ID mentioned in complaint (+5), counterparty match (+2), and type keyword match (+1).

---

## Case Type Routing

| case_type | department | typical severity |
|---|---|---|
| `wrong_transfer` | `dispute_resolution` | high |
| `payment_failed` | `payments_ops` | medium / high |
| `refund_request` | `dispute_resolution` or `customer_support` | low / medium |
| `duplicate_payment` | `payments_ops` | high |
| `merchant_settlement_delay` | `merchant_operations` | medium |
| `agent_cash_in_issue` | `agent_operations` | medium |
| `phishing_or_social_engineering` | `fraud_risk` | critical |
| `other` | `customer_support` | low |

---

## Assumptions

- Transaction history entries with null amounts or types are handled gracefully without crashing
- Complaints referencing amounts as words ("five hundred taka") may not be matched by the rule-based fallback but will be handled correctly by the LLM layers
- Duplicate payment detection at the rule-based level returns `insufficient_data` since a single transaction entry cannot confirm duplication alone
- The service treats all input as synthetic/test data — no real payment system integration

---

## Known Limitations

- Groq free tier has rate limits (30 req/min, 14,400/day) — sustained parallel load may trigger fallback to rule-based
- Bangla keyword coverage in the rule-based fallback is broad but not exhaustive for all regional dialects
- The rule-based fallback assigns `other` with 0.40 confidence when no keywords match — nuanced complaints without clear keywords will be underclassified at this layer
- The LLM cannot access real transaction system data — analysis is limited to the history provided in the request

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes (for LLM) | Groq API key — get free at console.groq.com |
| `PORT` | No | Server port (default: 8000) |

See `.env.example` for the template.

---

## No Real Customer Data

All complaints and transaction histories used during development and testing are synthetic. No real customer data, real payment APIs, or production systems were used at any point.

## No Secrets Committed

This repository contains no API keys, tokens, or credentials. The `GROQ_API_KEY` is stored only in the Render environment variables for the deployed service. The `.env` file is listed in `.gitignore` and `.dockerignore`.
