"""
FIOS Copilot — Decision Simulation Layer
Evaluates multiple strategic paths before the user acts, providing deterministic-LLM hybrid projections.
"""

import json
from typing import Dict, Any, List
from FIOS.copilot.ai import _call_ai, _parse_json_response

class DecisionSimulator:
    
    async def simulate_strategy(self, context: str) -> List[Dict[str, Any]]:
        """
        Simulate 3 strategic paths: Conservative (Safe), Balanced, Aggressive (Bold).
        """
        prompt = f"""You are a top-tier Upwork strategist. The freelancer needs to decide how to approach this job/conversation.
CONTEXT:
{context[:2000]}

Simulate 3 distinct strategic paths. Keep output highly concise. No essays.
Return ONLY a JSON array of 3 objects structured exactly like this:
[
  {{
    "path_name": "Conservative",
    "estimated_win_probability": "High/Medium/Low",
    "estimated_revenue": "Low/Average/High",
    "negotiation_risk": "Low",
    "client_stress_risk": "Low",
    "long_term_value_potential": "Medium",
    "reasoning": "1 concise sentence explaining why."
  }},
  {{
    "path_name": "Balanced",
    ...
  }},
  {{
    "path_name": "Aggressive",
    ...
  }}
]"""
        raw = await _call_ai(prompt)
        result = _parse_json_response(raw)
        
        if isinstance(result, list) and len(result) >= 3:
            # Map robustly to UI names
            try:
                result[0]["ui_label"] = "Safe"
                result[1]["ui_label"] = "Balanced"
                result[2]["ui_label"] = "Bold"
            except (IndexError, KeyError, TypeError):
                pass
            return result[:3]
            
        return []

    async def simulate_pricing(self, job_title: str, job_description: str, base_price: float) -> List[Dict[str, Any]]:
        """
        Simulate 3 pricing strategies given a calculated baseline point.
        """
        prompt = f"""You are an Upwork pricing psychological expert.
JOB: {job_title}
DETAILS: {job_description[:1500]}
ESTIMATED BASE PRICE: ${base_price}

Simulate 3 pricing options (Lower, Recommended, Premium) and project their impacts.
Return ONLY a JSON array of 3 objects structured exactly like this:
[
  {{
    "price_option": "Lower",
    "suggested_amount": number,
    "projected_success_likelihood": "High/Medium/Low",
    "projected_revenue_impact": "Loss/Stable/Gain",
    "negotiation_probability": "Low/Medium/High",
    "strategic_comment": "1 concise sentence on why choose this."
  }},
  {{
    "price_option": "Recommended",
    ...
  }},
  {{
    "price_option": "Premium",
    ...
  }}
]"""
        raw = await _call_ai(prompt)
        result = _parse_json_response(raw)
        return result if isinstance(result, list) else []

    async def simulate_negotiation(self, messages: str, client_pushback: str) -> List[Dict[str, Any]]:
        """
        Simulate 3 responses to a client pushback (e.g., holding firm, giving discount, reducing scope).
        """
        prompt = f"""The client has pushed back on the freelancer's terms. You must simulate 3 negotiation responses.
RECENT HISTORY:
{messages[-1000:]}

CLIENT PUSHBACK:
"{client_pushback}"

Simulate these 3 approaches: 
1. Hold Firm (No concessions)
2. Conditional Discount (Give a little, get a little)
3. Scope Reduction (Drop price by dropping deliverables)

Return ONLY a JSON array of 3 objects structured exactly like this:
[
  {{
    "approach": "Hold Firm",
    "projected_outcome": "Likely accepted/Likely rejected",
    "revenue_impact": "None/Positive/Negative",
    "relationship_impact": "Strain/Respect/Neutral",
    "risk_assessment": "1 sentence risk evaluation."
  }},
  ...
]"""
        raw = await _call_ai(prompt)
        result = _parse_json_response(raw)
        return result if isinstance(result, list) else []

simulator = DecisionSimulator()
