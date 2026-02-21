import json
from typing import Dict, Any, List

class OpportunityAgent:
    """
    FIOS Opportunity Scanner Agent
    Scores jobs based on win probability, budget, fit, and memory.
    """
    def __init__(self):
        self.agent_name = "opportunity_agent"

    async def analyze_job(
        self,
        job_data: Dict[str, Any],
        memory_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculates win probability and outputs recommendation
        """
        description = job_data.get("description", "").lower()
        title = job_data.get("title", "").lower()
        client_stats = job_data.get("client_stats", {})
        
        # Analyze fit
        fit_score = self._calculate_fit_score(description, title, memory_context)
        client_score = self._calculate_client_score(client_stats)
        
        # Calculate win probability
        win_prob = min(99, int((fit_score * 0.6) + (client_score * 0.4)))
        
        recommendation = "Apply" if win_prob > 65 else "Skip"
        
        hook = self._generate_hook(job_data, memory_context)
        
        return {
            "win_probability": win_prob,
            "strategic_fit_score": fit_score,
            "recommendation": recommendation,
            "suggested_hook": hook,
            "analysis_details": {
                "client_quality": client_score,
                "niche_match": fit_score
            }
        }

    def _calculate_fit_score(self, description: str, title: str, memory: Dict) -> int:
        brain = memory.get("brain_snapshot", {})
        skills = [s.lower() for s in brain.get("skills", [])]
        niches = [n.lower() for n in brain.get("niches", [])]
        
        score = 40  # Base score
        full_text = description + " " + title
        
        for skill in skills:
            if skill in full_text:
                score += 15
                
        for niche in niches:
            if niche in full_text:
                score += 20
                
        return min(100, score)

    def _calculate_client_score(self, client_stats: Dict) -> int:
        if not client_stats:
            return 50  # Unknown
            
        hire_rate = client_stats.get("hire_rate", 0)
        total_spent = client_stats.get("total_spent", 0)
        
        score = 30
        
        if hire_rate > 70:
            score += 40
        elif hire_rate > 50:
            score += 20
            
        if total_spent > 10000:
            score += 30
        elif total_spent > 1000:
            score += 15
            
        return min(100, score)

    def _generate_hook(self, job_data: Dict, memory: Dict) -> str:
        brain = memory.get("brain_snapshot", {})
        authority = brain.get("authority_level", "Expert")
        
        return f"As an {authority}, I specialize in exactly this type of project. Let me show you how I solved this for a similar client recently."
