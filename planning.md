A submission flows top-down through both signals in parallel, gets combined into a single confidence score, gets mapped to one of three label variants based on thresholds, and finally writes a structured entry to the audit log before returning. An appeal looks up the original decision by `content_id`, marks it for review, logs the appeal alongside the original decision, and confirms.

---

## Detection signals

### Signal 1: LLM-based classification

**What it measures:** semantic and stylistic coherence holistically. The model has been trained on billions of words and "knows" what human vs AI writing tends to feel like — pacing, surprise, idiosyncrasy, voice.

**Why this property differs:** AI text tends to be smoothly fluent, evenly paced, and surprisingly neutral in opinion. Human text has voice and idiosyncrasy that an LLM can detect even when it can't articulate why.

**Output format:** float between 0.0 (clearly human) and 1.0 (clearly AI). Prompt asks Groq's Llama 3.3 to return a structured JSON with `score` and a one-sentence reason.

**What it can't capture:** the LLM can be fooled by carefully edited AI text where a human has rephrased to add quirks. It's also worse on very short text (under ~50 words) because there isn't enough signal to assess voice.

### Signal 2: Stylometric heuristics

**What it measures:** measurable statistical properties of the text — sentence length variance, vocabulary diversity (type-token ratio), and punctuation density.

**Why this property differs:** AI text is statistically more uniform than human writing. Sentences cluster around an average length. Vocabulary is broader but less repetitive. Punctuation is more conventional. Humans are messier in ways that show up in the numbers.

**Output format:** float between 0.0 and 1.0. Compute three sub-metrics (sentence length variance, TTR, punctuation ratio), normalize each to 0-1, and average them into a single stylometric score.

**What it can't capture:** highly formal human writing (academic papers, legal text, technical documentation) will score as AI-like on stylometry because it's structurally uniform. The opposite is also true: an AI prompted to write casually with typos can fool stylometry.

### Why two signals, not one

The two signals capture genuinely different properties — one semantic, one structural. When they agree, confidence is high. When they disagree, that's the signal for "uncertain" — a borderline case that probably deserves human review.

---

## Uncertainty representation

The combined confidence score is a weighted average: `0.6 * llm_score + 0.4 * stylometric_score`.

**Why 60/40 in favor of LLM:** the LLM has access to richer semantic context. Stylometry is a strong support signal but is too easily fooled by formal-but-human writing to deserve equal weight.

### Threshold mapping

| Combined score | Label variant |
|---|---|
| `>= 0.75` | Likely AI-generated |
| `0.40 – 0.74` | Uncertain |
| `< 0.40` | Likely human-written |

The "uncertain" band is intentionally wide because false positives (calling a human's work AI) are worse than false negatives on a creative platform. A real human writer who gets falsely flagged loses trust in the platform. A real AI piece that slips through as "uncertain" gets human review, which is acceptable.

### How I'll validate the scores are meaningful

In Milestone 4 I'll test the scoring against 4 deliberately chosen inputs (clear AI, clear human, formal human, lightly edited AI). The score must vary noticeably between clear-AI and clear-human cases — if every input scores around 0.5, the scoring isn't actually capturing anything.

---

## Transparency label variants

These are the exact strings the API returns and the UI would render.

### High-confidence AI (score >= 0.75)
>  **Likely AI-generated.** Our system found strong signals that this content was produced by an AI model. The creator can appeal this label if it's incorrect.

### Uncertain (score 0.40 – 0.74)
>  **Uncertain attribution.** Our system found mixed signals. This content has been flagged for human review and may be either AI-assisted or human-written with a formal style. The creator can provide context through an appeal.

### High-confidence human (score < 0.40)
>  **Likely human-written.** Our system found strong signals that this content was produced by a human author.

All three include a brief, non-technical explanation. The "uncertain" label specifically explains *why* it's uncertain (mixed signals) instead of just being vague, because that distinction matters to the creator reading it.

---

## Appeals workflow

### Who can submit an appeal
The creator of the content (identified by `creator_id` from the original submission). For this MVP, we trust the `creator_id` in the request; in production, this would be tied to authenticated user identity.

### What they provide
- `content_id` (str): the unique ID returned by `/submit`
- `creator_reasoning` (str): free-text explanation of why the classification is wrong

### What the system does
1. Look up the original decision in the audit log by `content_id`
2. Update the entry's status from `classified` to `under_review`
3. Append a new audit log entry recording the appeal (timestamp, content_id, creator_reasoning)
4. Return confirmation to the creator: `{"status": "appeal_received", "content_id": "...", "review_status": "under_review"}`

### What a human reviewer would see
When the human review queue is opened (out of scope for this project), each entry would show: the original text, both signal scores, the combined confidence, the assigned label, the creator's reasoning, and a button to override or uphold the original decision.

This MVP does NOT implement automated re-classification on appeal. The lab explicitly does not require it.

---

## Anticipated edge cases

### Edge case 1: Formal human writing

A non-native English speaker writing academic prose, or an academic submitting an excerpt of a peer-reviewed paper. Their writing is statistically uniform (low sentence length variance, consistent punctuation) — exactly what stylometry flags as AI-like.

**How the system handles it:** the LLM signal is more likely to recognize the human voice and assign a low AI score. With the 60/40 weighting, the LLM dominates. If both signals disagree (LLM says human, stylometry says AI), the combined score should land in the "uncertain" band, which triggers the soft label and gives the creator a clean appeal path.

### Edge case 2: Lightly edited AI output

A writer takes ChatGPT output and lightly edits it — fixes a few sentences, changes word order, adds an em-dash. The text retains most of its AI signature but reads less mechanically.

**How the system handles it:** this is the hardest case. The LLM might score it as borderline human. Stylometry might still flag it as too uniform. The combined score likely lands in the "uncertain" band, which is the honest answer — the system isn't pretending to know what it can't know.

### Edge case 3: Very short submissions (< 50 words)

A tweet-length post or a haiku. Neither signal has enough text to make a confident judgment.

**How the system handles it:** flagged as uncertain by default. The label explicitly mentions short text as a possible reason. Long-term fix would be to refuse submissions under a length threshold, but for v1 we accept all inputs.

---

## API contract

### POST /submit

**Request:**
```json
{
  "text": "...",
  "creator_id": "test-user-1"
}
```

**Response:**
```json
{
  "content_id": "uuid-string",
  "attribution": "likely_ai | uncertain | likely_human",
  "confidence": 0.78,
  "llm_score": 0.81,
  "stylometric_score": 0.74,
  "label": " Likely AI-generated. ...",
  "timestamp": "2025-06-22T14:32:10Z"
}
```

### POST /appeal

**Request:**
```json
{
  "content_id": "uuid-string",
  "creator_reasoning": "I'm a non-native speaker..."
}
```

**Response:**
```json
{
  "status": "appeal_received",
  "content_id": "uuid-string",
  "review_status": "under_review"
}
```

### GET /log

**Response:**
```json
{
  "entries": [
    { "content_id": "...", "timestamp": "...", "attribution": "...", "confidence": 0.78, "llm_score": 0.81, "stylometric_score": 0.74, "status": "classified" },
    { ... }
  ]
}
```

---

## Audit log structure

Each entry is a JSON object. Stored as a list in a single JSON file (`audit_log.json`) for MVP simplicity. SQLite would be the production choice.

Required fields per entry:
- `timestamp` (ISO 8601)
- `content_id` (uuid)
- `creator_id` (str)
- `attribution` (str: "likely_ai" | "uncertain" | "likely_human")
- `confidence` (float)
- `llm_score` (float)
- `stylometric_score` (float)
- `status` (str: "classified" | "under_review")
- `appeal_reasoning` (str, only on appeal entries)

---

## Rate limiting

Submission endpoint limits:
- **10 requests per minute** per IP
- **100 requests per day** per IP

**Reasoning:** a real creator submitting their own work hits this endpoint at most a few times per writing session. 10/min comfortably accommodates testing and legitimate usage. 100/day is the daily ceiling — a creator submitting more than 100 distinct pieces in a day is either testing, abusive, or running automation. Blocking is preferable to allowing potential floods.

Other endpoints (`/appeal`, `/log`) are not rate limited in this MVP because appeals are rare per user and `/log` is for grading/debugging.

---

## AI Tool Plan

### Milestone 3 — Submission endpoint + first signal (LLM)

**What I'll give Claude Code:**
- My Detection Signals section (just Signal 1 spec)
- My Architecture diagram
- My API Contract section (just the `/submit` endpoint)

**What I'll ask it to generate:**
1. Flask app skeleton with `POST /submit` route stub
2. The LLM detection signal function (Groq + Llama 3.3) returning a score 0.0-1.0
3. A minimal audit log writer that appends to `audit_log.json`
4. A `GET /log` route that returns recent entries

**How I'll verify before wiring:**
- Call the LLM signal function directly with 3 test inputs (clearly AI, clearly human, neutral) and inspect the score
- Hit `/submit` with curl, confirm I get a structured JSON response with `content_id`
- Hit `/log`, confirm the entry was written correctly

### Milestone 4 — Second signal + confidence scoring

**What I'll give Claude Code:**
- My Detection Signals section (just Signal 2 spec)
- My Uncertainty Representation section (the weighting and thresholds)
- My architecture diagram

**What I'll ask it to generate:**
1. The stylometric signal function (sentence length variance + TTR + punctuation density)
2. The confidence scoring function combining both signals with the 60/40 weighting

**How I'll verify:**
- Test stylometric function on the same 3 inputs from Milestone 3 — does it produce a different signal than the LLM?
- Run all 4 lab-provided test inputs (clear AI, clear human, formal human, edited AI) through the full pipeline. The scores must vary meaningfully across them. If every input produces ~0.5, the scoring is broken.

### Milestone 5 — Production layer (labels + appeals + rate limit)

**What I'll give Claude Code:**
- My Transparency Label Variants section
- My Appeals Workflow section
- My Rate Limiting section

**What I'll ask it to generate:**
1. The label generation function (maps confidence score to label text)
2. The `POST /appeal` endpoint (look up, update status, log, respond)
3. Flask-Limiter setup with my chosen rate limits

**How I'll verify:**
- Submit text designed to hit each of the 3 label variants — confirm all 3 are reachable
- Submit an appeal for one of the content_ids — confirm `/log` shows status `under_review` and the appeal_reasoning is in the entry
- Hammer `/submit` with 12+ requests in a minute — confirm 429 responses appear after 10

---

## Spec reflection (placeholder — fill in after implementation)

This section will be completed in Milestone 6 after building. The reflection covers one way the spec helped guide implementation and one way the implementation diverged from it.