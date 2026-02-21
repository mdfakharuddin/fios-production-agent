from typing import Dict, Any, List
import datetime

class ConversationAgent:
    """
    FIOS Conversation Intelligence Agent

    Responsibilities:

    - Generate strategic client replies
    - Analyze client intent and tone
    - Detect ghosting risk
    - Suggest follow-ups
    - Apply freelancer voice profile
    - Use conversation memory
    """

    def __init__(self):
        self.agent_name = "conversation_agent"

    async def process_response(
        self,
        raw_response: str,
        strategy: Dict,
        memory_context: Dict
    ) -> str:
        # Apply voice profile
        response = self._apply_voice_profile(
            raw_response,
            memory_context
        )

        # Enhance authority using memory
        response = self._inject_authority_signals(
            response,
            memory_context
        )

        # Clean and optimize formatting
        response = self._optimize_structure(
            response
        )

        return response

    def analyze_conversation(
        self,
        client_message: str,
        memory_context: Dict
    ) -> Dict[str, Any]:
        intent = self._detect_client_intent(client_message)
        tone = self._detect_client_tone(client_message)
        ghost_risk = self._calculate_ghost_risk(memory_context)
        urgency = self._detect_urgency(client_message)

        return {
            "intent": intent,
            "tone": tone,
            "ghost_risk": ghost_risk,
            "urgency": urgency,
            "recommended_action": self._recommend_action(
                intent,
                ghost_risk,
                urgency
            )
        }

    def suggest_followup(
        self,
        conversation_history: List[Dict]
    ) -> Dict[str, Any]:
        last_message_time = self._get_last_message_time(
            conversation_history
        )

        if not last_message_time:
            return {"should_followup": False}

        hours_elapsed = (
            datetime.datetime.utcnow() - last_message_time
        ).total_seconds() / 3600

        if hours_elapsed > 24:
            return {
                "should_followup": True,
                "priority": "high",
                "reason": "Client inactive for over 24 hours",
                "recommended_message":
                "Following up to see if you had any thoughts on this. Happy to proceed whenever you're ready."
            }

        return {"should_followup": False}

    def _apply_voice_profile(
        self,
        response: str,
        memory_context: Dict
    ) -> str:
        brain = memory_context.get(
            "brain_snapshot",
            {}
        )
        voice = brain.get(
            "voice_profile",
            {}
        )
        tone = voice.get(
            "tone",
            "confident"
        )

        if tone == "confident":
            replacements = {
                "I think": "I recommend",
                "maybe": "",
                "I can do": "I will handle",
                "I could": "I can",
                "let me know": "let me know and I will proceed immediately"
            }

            for old, new in replacements.items():
                response = response.replace(old, new)

        return response

    def _inject_authority_signals(
        self,
        response: str,
        memory_context: Dict
    ) -> str:
        proposals = memory_context.get(
            "proposals",
            []
        )

        winning_count = len([
            p for p in proposals
            if isinstance(p, dict)
            and p.get("status") == "won"
        ])

        if winning_count > 0:
            authority_line = f"\n\nI’ve successfully handled similar projects before, and I can ensure a smooth and efficient execution."
            response = response + authority_line

        return response

    def _optimize_structure(
        self,
        response: str
    ) -> str:
        lines = response.split("\n")
        cleaned = []

        for line in lines:
            line = line.strip()

            if line:
                cleaned.append(line)

        return "\n\n".join(cleaned)

    def _detect_client_intent(
        self,
        message: str
    ) -> str:
        message_lower = message.lower()

        if any(x in message_lower for x in [
            "price",
            "cost",
            "budget"
        ]):
            return "pricing"

        if any(x in message_lower for x in [
            "timeline",
            "deadline",
            "when"
        ]):
            return "timeline"

        if any(x in message_lower for x in [
            "available",
            "can you",
            "are you able"
        ]):
            return "availability"

        if any(x in message_lower for x in [
            "start",
            "begin"
        ]):
            return "start_project"

        return "general"

    def _detect_client_tone(
        self,
        message: str
    ) -> str:
        message_lower = message.lower()

        if "urgent" in message_lower:
            return "urgent"

        if "?" in message:
            return "inquisitive"

        return "neutral"

    def _detect_urgency(
        self,
        message: str
    ) -> str:
        urgent_words = [
            "urgent",
            "asap",
            "immediately",
            "today"
        ]

        for word in urgent_words:
            if word in message.lower():
                return "high"

        return "normal"

    def _calculate_ghost_risk(
        self,
        memory_context: Dict
    ) -> str:
        conversations = memory_context.get(
            "conversations",
            []
        )

        if not conversations:
            return "unknown"

        last = conversations[0]
        last_time = last.get("last_message_time")

        if not last_time:
            return "unknown"

        hours = (
            datetime.datetime.utcnow() -
            datetime.datetime.fromisoformat(last_time)
        ).total_seconds() / 3600

        if hours > 48:
            return "high"

        if hours > 24:
            return "medium"

        return "low"

    def _recommend_action(
        self,
        intent: str,
        ghost_risk: str,
        urgency: str
    ) -> str:
        if urgency == "high":
            return "respond_immediately"
        if ghost_risk == "high":
            return "send_followup"
        if intent == "pricing":
            return "provide_quote"
        if intent == "timeline":
            return "provide_timeline"

        return "respond_normally"

    def _get_last_message_time(
        self,
        history: List[Dict]
    ):
        if not history:
            return None

        last = history[-1]
        timestamp = last.get("timestamp")

        if not timestamp:
            return None

        return datetime.datetime.fromisoformat(timestamp)
