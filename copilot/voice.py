"""
FIOS Copilot — Voice Lock & Tone Consistency Engine

Extracts the freelancer's specific communication style from past wins
and aggressively enforces it during AI generation to eliminate
generic "AI-speak" (delve, robust, tapestry, etc.).
"""

import json
import os
import time
from typing import Dict, Any, List

VOICE_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "freelancer_voice_profile.json")

# ── FORBIDDEN AI WORDS ──
FORBIDDEN_WORDS = [
    "delve", "tapestry", "robust", "crucial", "testament", "realm", "bustling",
    "in summary", "moreover", "furthermore", "vital", "paramount", "leverage",
    "synergy", "paradigm", "navigating", "seamlessly"
]

class VoiceLockEngine:
    
    def __init__(self):
        self._cached_profile = None

    def get_voice_profile(self) -> Dict[str, Any]:
        """Load the stored voice profile."""
        if self._cached_profile:
            return self._cached_profile
            
        if os.path.exists(VOICE_PROFILE_PATH):
            try:
                with open(VOICE_PROFILE_PATH, "r", encoding="utf-8") as f:
                    self._cached_profile = json.load(f)
                    return self._cached_profile
            except Exception as e:
                print(f"[VoiceLock] Error loading profile: {e}")
                
        # Fallback empty profile
        return {
            "formality_level": "professional yet direct",
            "directness_score": 8,
            "confidence_level": "high",
            "emoji_usage": "none",
            "writing_constraints": "Use simple, direct language. Avoid corporate buzzwords."
        }

    def get_voice_conditioning_prompt(self, mode: str = "conversation", strict: bool = True) -> str:
        """
        Build the conditioning block to inject into AI prompts.
        """
        if not strict:
            return "Note: Maintain a professional freelancer tone."

        profile = self.get_voice_profile()
        
        # Base constraints from profile
        constraints = [
            f"Formality: {profile.get('formality_level', 'Direct')}",
            f"Confidence: {profile.get('confidence_level', 'High')}",
            f"Emoji Use: {profile.get('emoji_usage', 'Minimal')}",
            f"Style: {profile.get('writing_constraints', 'Direct and concise')}"
        ]
        
        # Specific mode adjustments
        if mode == "conversation":
            constraints.append("Message Style: Short, casual but professional, highly conversational. Never sound like a formal email.")
        elif mode == "proposal":
            constraints.append("Proposal Style: Confident hook, specific value proposition, strong clear CTA. Zero fluff.")
        elif mode == "negotiation":
            constraints.append("Negotiation Style: Firm on value, polite, clear boundaries. Do not grovel.")

        # Hard anti-AI rules
        anti_ai_rules = "NEVER use these words: " + ", ".join(FORBIDDEN_WORDS) + "."

        block = f"""
CRITICAL RULE: STRICT VOICE LOCK ENABLED
You must perfectly mimic the user's historical writing tone.
{chr(10).join('- ' + c for c in constraints)}
{anti_ai_rules}
If you sound like a standard AI assistant, you have failed. Be direct, human, and concise.
"""
        return block

    def check_and_adjust_draft(self, draft: str, strict: bool = True) -> Dict[str, Any]:
        """
        Fast deterministic check for AI-speak deviations.
        """
        if not draft or not strict:
            return {"adjusted_draft": draft, "deviation_score": 0, "flags": []}
            
        flags = []
        lower_draft = draft.lower()
        
        # 1. Forbidden word detection
        used_forbidden = [w for w in FORBIDDEN_WORDS if w in lower_draft]
        if used_forbidden:
            flags.append(f"AI buzzwords detected: {', '.join(used_forbidden)}")
            
        # 2. Structure detection (Too long for chat)
        if len(draft.split()) > 150:
            flags.append("Draft is unusually long, risking an automated feel.")
            
        # 3. Opening detection
        if "i hope this message finds you well" in lower_draft:
            flags.append("Generic automated opening detected.")

        score = min(100, len(flags) * 30)

        return {
            "adjusted_draft": draft, # We leave adjustment to the AI generation side or warn the user
            "deviation_score": score,
            "flags": flags
        }

    async def extract_voice_profile(self) -> Dict[str, Any]:
        """
        Heavy analytics task: Compute the voice profile from past data.
        Usually run via background task.
        """
        from FIOS.database.connection import async_session_maker
        from FIOS.database.models.jobs import Job
        from FIOS.database.models.conversations import Conversation
        from FIOS.copilot.ai import copilot_ai
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        t0 = time.time()
        
        proposals_text = []
        conversations_text = []
        
        async with async_session_maker() as session:
            # Get wins
            result = await session.execute(
                select(Job).where(Job.outcome == "WON").options(selectinload(Job.proposals)).limit(20)
            )
            jobs = result.scalars().all()
            for j in jobs:
                if j.proposals:
                    for p in j.proposals:
                        if p.cover_letter:
                            proposals_text.append(p.cover_letter[:1000])

            # Get successful conversations (we assume all synced threads are useful signals)
            result = await session.execute(
                select(Conversation).limit(20)
            )
            convos = result.scalars().all()
            for c in convos:
                msgs = c.messages_json or []
                # Only care about freelancer's own messages to learn their voice
                my_msgs = [m.get("text", "") for m in msgs if m.get("sender", "") == "user"]
                if my_msgs:
                    conversations_text.append("\n".join(my_msgs[-5:]))

        if not proposals_text and not conversations_text:
            return {"status": "error", "message": "Not enough data to build voice profile."}

        # Combine corpus into a dense sample
        dense_corpus = "PROPOSALS:\n" + "\n---\n".join(proposals_text[:5]) + "\n\nCHAT:\n" + "\n---\n".join(conversations_text[:5])
        
        prompt = f"""You are a master linguistic profiler. Analyze the following actual proposals and chat messages written by a freelancer.
Extract their exact writing style, tone, and structural preferences so an AI can perfectly mimic them.

CORPUS:
{dense_corpus[:5000]}

Return ONLY a JSON object:
{{
  "average_sentence_length": "short/medium/long",
  "formality_level": "e.g. casual professional, highly formal, extremely direct",
  "directness_score": 1-10 (10 being highly direct, no fluff),
  "confidence_level": "how they express expertise",
  "emoji_usage": "frequency and type of emojis used",
  "question_frequency": "do they ask lots of questions or make statements?",
  "CTA_style": "how do they close? pushy, soft, assumptive?",
  "writing_constraints": "Compile a 2-3 sentence strict instruction block on how to write EXACTLY like this person. Mention what to avoid."
}}"""

        from FIOS.copilot.ai import _call_ai, _parse_json_response
        raw = await _call_ai(prompt)
        profile = _parse_json_response(raw)
        
        if profile and "formality_level" in profile:
            os.makedirs(os.path.dirname(VOICE_PROFILE_PATH), exist_ok=True)

            with open(VOICE_PROFILE_PATH, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2)
            self._cached_profile = profile
            
        elapsed = round((time.time() - t0) * 1000, 1)
        
        return {
            "status": "ok",
            "profile": profile,
            "compute_time_ms": elapsed
        }

# Global instance
voice_engine = VoiceLockEngine()
