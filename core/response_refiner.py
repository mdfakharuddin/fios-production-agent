from typing import Dict, Any, List

class ResponseRefiner:
    """
    Final output optimization layer
    """

    def __init__(self):
        pass

    async def refine(
        self,
        response: str,
        strategy: Dict,
        brain_context: str
    ) -> str:
        response = self._remove_weak_language(response)
        response = self._improve_confidence(response)
        response = self._optimize_formatting(response)

        return response

    def _remove_weak_language(
        self,
        text: str
    ) -> str:
        weak_phrases = [
            "I think",
            "maybe",
            "possibly",
            "I believe",
            "I hope"
        ]

        for phrase in weak_phrases:
            text = text.replace(phrase, "")

        return text

    def _improve_confidence(
        self,
        text: str
    ) -> str:
        replacements = {
            "I can help": "I will handle this",
            "I can do this": "I will execute this",
            "I am able to": "I will"
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    def _optimize_formatting(
        self,
        text: str
    ) -> str:
        lines = text.split("\n")
        cleaned = []

        for line in lines:
            line = line.strip()
            if line:
                cleaned.append(line)

        return "\n\n".join(cleaned)

    def score_proposal(
        self,
        proposal: str
    ) -> Dict[str, Any]:
        """
        Calculates Win Probability before sending by scanning Proposal logic against constraints.
        """
        score = 85
        weak_areas = []
        improvements = []
        
        proposal_lower = proposal.lower()
        
        # Analyze Confidence Language
        if "i think" in proposal_lower or "maybe" in proposal_lower:
            score -= 10
            weak_areas.append("Confidence Language")
            improvements.append("Replace weak phrasing ('I think', 'maybe') with declarative recommendations.")

        # Analyze CTA
        if "call" not in proposal_lower and "discuss" not in proposal_lower:
            score -= 15
            weak_areas.append("CTA Strength")
            improvements.append("Add a clearer Call-to-Action offering a brief discovery call.")
        
        # Analyze Authority referencing 
        if "example" not in proposal_lower and "portfolio" not in proposal_lower and "similar" not in proposal_lower:
            score -= 5
            weak_areas.append("Authority Strength")
            improvements.append("Include specific references or links to similar past work.")
            
        return {
            "win_probability": max(0, min(100, score)),
            "weak_areas": weak_areas,
            "recommended_improvements": improvements
        }
