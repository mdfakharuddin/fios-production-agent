import re
from typing import Dict, Any, List

class StrategyEngine:
    """
    FIOS Strategic Decision Engine

    Determines:
    - Which agent to use
    - What objective to execute
    - Priority level
    - Execution mode
    """

    def __init__(self):
        self.agent_map = {
            "proposal": "proposal_agent",
            "conversation": "conversation_agent",
            "analysis": "intelligence_agent",
            "memory": "memory_agent",
            "project": "project_agent",
            "general": "conversation_agent"
        }

    async def determine_strategy(
        self,
        user_input: str,
        memory_context: Dict,
        brain_context: str
    ) -> Dict[str, Any]:

        intent = self._detect_intent(user_input)
        agent = self.agent_map.get(intent, "conversation_agent")
        objective = self._build_objective(intent, user_input)
        priority = self._calculate_priority(intent, memory_context)
        mode = self._determine_mode(intent)

        return {
            "intent": intent,
            "agent": agent,
            "objective": objective,
            "priority": priority,
            "mode": mode
        }

    def _detect_intent(self, text: str) -> str:
        text_lower = text.lower()

        proposal_patterns = [
            "write proposal",
            "create proposal",
            "job proposal",
            "apply job",
            "proposal for"
        ]

        conversation_patterns = [
            "reply",
            "respond",
            "client said",
            "message",
            "chat"
        ]

        analysis_patterns = [
            "analyze",
            "analysis",
            "review client",
            "client profile",
            "win probability"
        ]

        project_patterns = [
            "create project",
            "new project",
            "manage project",
            "track project"
        ]

        if self._match_patterns(text_lower, proposal_patterns):
            return "proposal"

        if self._match_patterns(text_lower, conversation_patterns):
            return "conversation"

        if self._match_patterns(text_lower, analysis_patterns):
            return "analysis"

        if self._match_patterns(text_lower, project_patterns):
            return "project"

        return "general"

    def _match_patterns(
        self,
        text: str,
        patterns: List[str]
    ) -> bool:
        for pattern in patterns:
            if pattern in text:
                return True
        return False

    def _build_objective(
        self,
        intent: str,
        user_input: str
    ) -> str:
        objectives = {
            "proposal": "Generate high-conversion freelance proposal optimized for client psychology and win probability.",
            "conversation": "Generate strategic reply optimized for trust, authority, and client engagement.",
            "analysis": "Analyze client, job, or conversation and provide strategic intelligence.",
            "project": "Create or manage freelance project with proper tracking and structure.",
            "general": "Provide intelligent assistance aligned with freelancer goals."
        }

        return objectives.get(intent, objectives["general"])

    def _calculate_priority(
        self,
        intent: str,
        memory_context: Dict
    ) -> str:
        if intent == "proposal":
            return "high"
        if intent == "conversation":
            return "high"
        if intent == "analysis":
            return "medium"
        if intent == "project":
            return "medium"

        return "normal"

    def _determine_mode(
        self,
        intent: str
    ) -> str:
        modes = {
            "proposal": "creation",
            "conversation": "communication",
            "analysis": "analysis",
            "project": "execution",
            "general": "assistance"
        }

        return modes.get(intent, "assistance")

    async def extract_learning_insights(
        self,
        memory: List[Dict]
    ) -> Dict:
        insights = {
            "common_patterns": [],
            "successful_topics": [],
            "client_behavior_patterns": []
        }

        for item in memory:
            content = item.get("content", "")

            if "proposal" in content.lower():
                insights["common_patterns"].append("proposal_activity")
            if "client" in content.lower():
                insights["client_behavior_patterns"].append("client_engagement")

        return insights

    async def detect_followups(
        self,
        conversations: List[Dict]
    ) -> List[Dict]:
        followups = []

        for convo in conversations:
            if convo.get("last_reply_hours", 0) > 24:
                followups.append({
                    "conversation_id": convo.get("id"),
                    "recommended_action": "send_followup",
                    "priority": "high"
                })

        return followups
