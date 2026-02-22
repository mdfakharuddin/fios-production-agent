"""
FIOS Research Agent — Deep Analysis Layer

This agent performs deeper research into job opportunities, clients, and market alignment.
It is designed to run as a standalone service (on Coolify) or be called by n8n.
"""

import json
import httpx
from typing import Dict, Any
from copilot.ai import _call_ai, SYSTEM_ROLE

class ResearchAgent:
    async def analyze_market_alignment(self, job_data: Dict[str, Any], brain_data: Dict[str, Any]) -> Dict[str, Any]:
        """Deep research into how this job fits the freelancer's specific niche."""
        
        prompt = f"""PERFORM DEEP MARKET RESEARCH.

FREELANCER BRAIN:
{json.dumps(brain_data.get('freelancer', {}), indent=2)}

JOB DETAILS:
{json.dumps(job_data, indent=2)}

TASK:
1. Identify the 'hidden' requirements not explicitly mentioned.
2. Estimate the competitive density (how many others have these specific skills).
3. Suggest the #1 'angle' to win this job.

Return JSON:
{{
  "hidden_requirements": ["list", "of", "likely", "unspoken", "needs"],
  "competitive_moat": "description of why the freelancer is uniquely qualified",
  "winning_angle": "the specific hook to use in the proposal",
  "estimated_value_multiplier": 1.0,
  "strategic_priority": "CRITICAL" | "HIGH" | "NORMAL" | "LOW"
}}"""

        raw = await _call_ai(prompt, SYSTEM_ROLE)
        try:
            # Simple extraction from possible markdown
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            return json.loads(raw)
        except Exception:
            return {"error": "Failed to parse research output", "raw": raw}

research_agent = ResearchAgent()
