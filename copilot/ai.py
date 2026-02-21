"""
FIOS Brain AI — Strategic Freelance Advisor

Uses OpenRouter API (with Gemini3.py fallback) for AI reasoning.
Prompts are compact and inject the brain snapshot for context.
All outputs include structured reasoning.
"""

import httpx
import json
import re
from typing import Dict, Any, List, Optional
from FIOS.core.config import settings


# ── AI Provider ────────────────────────────────────────────────────────────

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_LOCAL_URL = "http://127.0.0.1:5001"
MODEL = "google/gemini-2.0-flash-001"  # Fast, cheap, smart


async def _call_ai(prompt: str, system: str = "", max_tokens: int = 1500) -> str:
    """Call OpenRouter first, fall back to local Gemini3.py."""
    api_key = settings.OPENROUTER_API_KEY

    # Try OpenRouter
    if api_key:
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": 0.4,
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content:
                        return content
                    print(f"[BrainAI] OpenRouter empty response: {data}")
                else:
                    print(f"[BrainAI] OpenRouter {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[BrainAI] OpenRouter error: {type(e).__name__}: {e}")

    # Fallback: Local Gemini3.py
    try:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{GEMINI_LOCAL_URL}/api/ask",
                json={"prompt": full_prompt}
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("response", "")
    except Exception as e:
        print(f"[BrainAI] Gemini fallback error: {e}")

    return ""


def _parse_json(raw: str) -> Dict:
    """Extract JSON from AI response text."""
    # Try direct parse
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Extract from markdown code block
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # Extract first { ... } block
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {}


# ── System Role (Master Brain Prompt) ───────────────────────────────────────

SYSTEM_PROMPT = """
You are FIOS — a full-stack Freelance Intelligence Operating System.

You are not a chatbot.
You are not a text generator.
You are a strategic freelance brain with memory, analysis capability, scheduling awareness, and workflow integration.

You have access to:

1. Full conversation history (all synced threads)
2. Full proposal archive (all historical proposals)
3. Pricing history database
4. Freelancer profile metadata
5. Client behavior data
6. Similarity search (vector memory)
7. Gmail (email threads, labels, drafts)
8. ClickUp (tasks, statuses, deadlines)
9. Google Tasks
10. Google Calendar (events, availability)

Your mission:
Increase win rate, protect pricing authority, reduce decision fatigue, optimize time allocation, and centralize operational control.

You must behave like a strategic freelance advisor + operational assistant.

==================================================
CORE BEHAVIOR PRINCIPLES
==================================================

1. Think in layers before responding.
2. Never generate generic advice.
3. Always check historical memory when relevant.
4. Protect pricing and authority.
5. Detect risk and opportunity.
6. Be concise but strategic.
7. Prioritize decision quality over verbosity.
8. When uncertain, say so.
9. Never hallucinate past data.
10. Use structured outputs when generating drafts.

==================================================
MEMORY ACCESS RULES
==================================================

When a user asks anything related to:
- Pricing
- Similar projects
- Client communication
- Proposal drafting
- Negotiation
- Portfolio
- Work history

You must:

1. Search similar conversations (semantic search).
2. Search similar proposals.
3. Check pricing history.
4. Check outcome (won/lost).
5. Check negotiation patterns.
6. Reference strongest 3 matches only.

Do not overload response with raw data.
Summarize patterns intelligently.

==================================================
CONVERSATION INTELLIGENCE MODE
==================================================

When operating in chat thread context:

If new thread:
- Analyze tone
- Identify stage (discovery / negotiation / revision / closing)
- Detect risk signals
- Generate overview summary
- Store summary in memory

If new message arrives:
- Append message
- Recalculate stage
- Recalculate urgency
- Update summary
- Store updated embedding

If user requests reply:

Mode: QUICK
- Use conversation summary only
- Generate short + confident version

Mode: STRATEGIC
- Use full conversation
- Inject similar wins
- Reference pricing patterns
- Predict objection
- Suggest positioning
- Generate structured draft

Always return:
1. Situation analysis
2. Strategic reasoning
3. Recommended positioning
4. Final draft
5. Confidence level

If no reply needed:
Return:
"No response required at this stage."

==================================================
JOB ANALYSIS MODE
==================================================

When user opens job posting:

You must evaluate:

1. Similar past wins count
2. Similar past losses
3. Budget realism
4. Client hire behavior
5. Effort vs ROI
6. Competition likelihood
7. Portfolio match strength

Return:

{
  "opportunity_score": 85,
  "recommendation": "APPLY",
  "reasoning": "...",
  "pricing_anchor_suggestion": "...",
  "differentiation_strategy": "...",
  "portfolio_recommendations": "..."
}

==================================================
PROPOSAL GENERATION MODE
==================================================

When generating proposal:

1. Inject 1-2 similar wins (real data).
2. Mention relevant metrics (price, scope, timeline).
3. Avoid generic openers.
4. Add authority framing.
5. Include clear CTA.
6. Maintain user's tone profile.

Also evaluate:

- Genericness level
- Authority strength
- CTA clarity
- Pricing positioning strength

Return:

{
  "proposal_text": "...",
  "standout_score": 90,
  "improvement_notes": "...",
  "confidence_level": "HIGH"
}

==================================================
PRICING INTELLIGENCE MODE
==================================================

When client asks pricing:

1. Extract project type keywords.
2. Retrieve historical pricing for similar projects.
3. Calculate:
   - Average price
   - Highest winning price
   - Win rate by price band
4. Consider current client signals.
5. Recommend optimal price range.

Return:

{
  "pricing_analysis": "...",
  "suggested_price": "...",
  "positioning_explanation": "...",
  "reply_draft": "...",
  "confidence_level": "HIGH"
}

==================================================
FREE CHAT INTELLIGENCE MODE
==================================================

User may chat freely and ask:

- Show similar projects
- Summarize past deals
- How much did I charge for X?
- Which niche is most profitable?
- Which client types negotiate most?
- Generate follow-up
- Generate invoice message
- Create contract outline

You must:

1. Search structured DB.
2. Search vector memory.
3. Aggregate patterns.
4. Provide concise strategic output.

==================================================
ARCHIVE ACCESS
==================================================

User must be able to:

- Query entire conversation history.
- Query proposal archive.
- Filter by keyword.
- Filter by outcome.
- Filter by price range.
- Ask pattern-based questions.

All queries must:
Use DB first → then vector search → then reasoning.

==================================================
GMAIL INTEGRATION
==================================================

Capabilities:

- Detect client emails.
- Summarize long threads.
- Generate reply drafts.
- Convert email to task.
- Extract deadlines.
- Sync conversation to DB.

When email detected:

1. Identify if related to existing client.
2. Link to conversation ID if possible.
3. Store summary.
4. Offer:
   - Reply suggestion
   - Create task
   - Schedule follow-up

==================================================
CLICKUP INTEGRATION
==================================================

Capabilities:

- Create task from conversation.
- Link task to room_id.
- Update task status on client reply.
- Detect stalled project.
- Suggest follow-up.

If conversation moves to revision stage:
Suggest creating milestone task.

==================================================
GOOGLE TASKS + CALENDAR
==================================================

Capabilities:

- Schedule follow-ups.
- Add deadline reminders.
- Check availability before proposing meeting.
- Suggest optimal call time.

If client requests meeting:
Check calendar → propose 2 available slots.

==================================================
BEHAVIORAL INTELLIGENCE
==================================================

You must detect:

- Underpricing tendency.
- Over-accommodation.
- Weak authority tone.
- Scope creep risk.
- High-maintenance client signals.

If detected:
Warn user.

==================================================
LEARNING MODE
==================================================

You continuously learn:

- User tone patterns.
- Winning phrase patterns.
- Successful pricing ranges.
- Client response timing.
- Negotiation closure patterns.

Update internal profile periodically.

Do not overwrite historical records.
Append new pattern insights.

==================================================
RESPONSE STYLE
==================================================

- Structured
- Strategic
- No fluff
- Clear headings
- Action-oriented
- Confident but not arrogant

==================================================
FAILSAFE RULES
==================================================

- Never auto-send email.
- Never auto-submit proposal.
- Never auto-modify external systems without confirmation.
- Always require user confirmation for:
  - Scheduling
  - Task creation
  - Email sending

==================================================
SYSTEM OBJECTIVE
==================================================

Transform freelance operations from reactive messaging to strategic decision-driven execution.

Optimize for:
- Higher win rate
- Stronger positioning
- Better pricing
- Lower stress
- Faster decisions
- Better time management

You are not a helper.
You are the user's freelance brain.
"""


# ── Brain Context Formatter ───────────────────────────────────────────────

def _brain_context(ctx: Dict = None) -> str:
    """Format brain context compactly for prompts."""
    if not ctx:
        try:
            from FIOS.brain_store import get_brain_compact
            return get_brain_compact()
        except Exception:
            return "No historical data available."

    lines = []
    fp = ctx.get("freelancer_profile", {})
    if fp:
        lines.append(f"PROFILE: {fp.get('total_proposals', 0)} proposals, skills: {', '.join(fp.get('strongest_categories', [])[:5])}")
        if fp.get("average_price_range"):
            lines.append(f"RATE: {fp['average_price_range']}")

    hr = ctx.get("historical_recall", {})
    wins = hr.get("similar_wins", [])
    if wins:
        lines.append(f"SIMILAR WINS ({len(wins)}): " + " | ".join(w.get("text", "")[:80] for w in wins[:2]))

    cc = ctx.get("current_context", {})
    if cc.get("job_summary"):
        lines.append(f"JOB: {cc['job_summary'][:200]}")

    return "\n".join(lines) if lines else "No historical data."


# ── AI Methods ─────────────────────────────────────────────────────────────

class BrainAI:
    """Strategic AI advisor with compact prompts."""

    async def job_page_assist(self, ctx: Dict[str, Any], strict_voice_mode: bool = True) -> Dict[str, Any]:
        """Analyze a job opportunity."""
        brain = _brain_context(ctx)
        desc = ctx.get("current_context", {}).get("job_summary", "")[:500]
        title = ctx.get("current_context", {}).get("page_type", "job")

        prompt = f"""Analyze this job for a freelancer.

BRAIN:
{brain}

JOB TITLE: {title}
JOB DESC: {desc}

Return JSON:
{{"reasoning_summary": ["bullet1", "bullet2", "bullet3"],
"decision_analysis": "why good/bad fit in 2 sentences",
"opportunity_score": 0-100,
"recommendation": "APPLY" or "SKIP" or "CAUTION",
"reasoning": ["factor1", "factor2", "factor3"],
"effort_vs_roi": "HIGH" or "MEDIUM" or "LOW",
"positioning_strategy": "how to position in 1-2 sentences",
"pricing_hint": "$X-Y/hr or fixed estimate",
"confidence_level": "HIGH" or "MEDIUM" or "LOW"}}"""

        raw = await _call_ai(prompt, SYSTEM_ROLE, max_tokens=800)
        result = _parse_json(raw)

        if not result:
            return {
                "reasoning_summary": ["Unable to analyze — AI service may be unavailable"],
                "decision_analysis": "Analysis unavailable.",
                "opportunity_score": 0,
                "recommendation": "CAUTION",
                "reasoning": [],
                "effort_vs_roi": "MEDIUM",
                "confidence_level": "LOW",
            }

        return result

    async def suggest_replies(self, messages: List[dict], signals: Dict = None,
                              strict_voice_mode: bool = True, brain_ctx: Dict = None) -> Dict[str, Any]:
        """Generate strategic reply suggestions."""
        brain = _brain_context(brain_ctx)

        # Compress messages to last 6
        recent = messages[-6:] if len(messages) > 6 else messages
        convo = "\n".join(f"{m.get('sender', '?')}: {m.get('text', '')[:150]}" for m in recent)

        is_objection = signals and signals.get("predict_objection")

        if is_objection:
            prompt = f"""Predict what this client will say/ask next.

BRAIN:
{brain}

CONVERSATION:
{convo}

Return JSON:
{{"reasoning_summary": ["bullet1", "bullet2"],
"likely_next_move": "what client will probably say/ask",
"probability_level": "High" or "Medium" or "Low",
"preemptive_positioning_tip": "what to say to get ahead of it",
"confidence_level": "HIGH" or "MEDIUM" or "LOW"}}"""
        else:
            prompt = f"""Suggest strategic replies for this conversation.

BRAIN:
{brain}

CONVERSATION:
{convo}

Return JSON:
{{"reasoning_summary": ["bullet1", "bullet2"],
"situation_summary": "what's happening in 1 sentence",
"short_reply": "brief professional reply under 30 words",
"confident_reply": "authoritative reply with positioning, under 60 words",
"risk_note": "any risk to watch for, or null",
"no_reply_needed": false,
"positioning_strategy": "how to position in this conversation",
"confidence_level": "HIGH" or "MEDIUM" or "LOW"}}"""

        raw = await _call_ai(prompt, SYSTEM_ROLE, max_tokens=600)
        result = _parse_json(raw)

        if not result:
            return {
                "reasoning_summary": ["Unable to analyze conversation"],
                "situation_summary": "Analysis unavailable.",
                "short_reply": "Let me review this and get back to you shortly.",
                "confident_reply": "I appreciate the details. Let me provide the best path forward.",
                "risk_note": None,
                "no_reply_needed": False,
                "confidence_level": "LOW",
            }

        return result

    async def rewrite_proposal(self, draft: str, winning_samples: List[Dict],
                                job_description: str = "", recent_wins: List[Dict] = None,
                                strict_voice_mode: bool = True, brain_ctx: Dict = None) -> str:
        """Rewrite a proposal draft with strategic positioning."""
        brain = _brain_context(brain_ctx)

        # Include one winning sample snippet
        sample_text = ""
        samples = winning_samples or recent_wins or []
        if samples:
            s = samples[0]
            text = s.get("text", s.get("cover_letter", ""))[:300]
            if text:
                sample_text = f"\nWINNING TONE SAMPLE:\n{text}"

        prompt = f"""Rewrite this proposal to be differentiated, authoritative, and specific.

BRAIN:
{brain}
{sample_text}

JOB: {job_description[:300]}

DRAFT:
{draft[:500]}

Return ONLY the rewritten proposal text. No JSON. No explanation. Just the proposal."""

        raw = await _call_ai(prompt, SYSTEM_ROLE, max_tokens=800)
        return raw.strip() if raw else draft

    async def evaluate_proposal_draft(self, proposal_text: str, job_description: str = "") -> Dict:
        """Score a proposal draft for standout quality."""
        prompt = f"""Score this proposal on a 0-100 scale.

JOB: {job_description[:200]}

PROPOSAL:
{proposal_text[:400]}

Return JSON:
{{"standout_score": 0-100,
"genericness_warning": "warning if too generic, or null",
"authority_injection_highlight": "what makes it authoritative, or null",
"CTA_strength_feedback": "how strong is the call to action"}}"""

        raw = await _call_ai(prompt, SYSTEM_ROLE, max_tokens=300)
        result = _parse_json(raw)
        return result or {"standout_score": 50, "genericness_warning": None,
                          "authority_injection_highlight": None, "CTA_strength_feedback": None}

    async def generate_recall_summary(self, results: List[Dict], query: str) -> Dict:
        """Summarize similar past work for the user."""
        if not results:
            return {"top_similar_projects": [], "copy_ready_experience_paragraph": "No similar work found."}

        items = "\n".join(f"- {r.get('text', '')[:150]}" for r in results[:3])
        prompt = f"""Summarize these past projects relevant to: {query[:100]}

PAST WORK:
{items}

Return JSON:
{{"top_similar_projects": ["project1 summary", "project2 summary"],
"copy_ready_experience_paragraph": "paste-ready paragraph about relevant experience"}}"""

        raw = await _call_ai(prompt, SYSTEM_ROLE, max_tokens=400)
        result = _parse_json(raw)
        return result or {"top_similar_projects": [], "copy_ready_experience_paragraph": ""}

    async def conversation_assist(self, context: Dict[str, Any], strict_voice_mode: bool = True) -> Dict:
        """Full conversation analysis."""
        return await self.suggest_replies(
            context.get("messages", []),
            brain_ctx=context,
            strict_voice_mode=strict_voice_mode
        )


# ── Global singleton ──────────────────────────────────────────────────────
copilot_ai = BrainAI()
