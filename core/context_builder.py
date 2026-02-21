from typing import Dict, Any, List
import json


class ContextBuilder:
    """
    FIOS Brain Context Builder

    Responsibilities:

    - Convert raw memory into structured intelligence context
    - Prioritize relevant proposals and conversations
    - Inject voice profile and authority level
    - Prepare optimized system context for LLM
    """

    def __init__(self):

        self.max_proposals = 3
        self.max_conversations = 3
        self.max_clients = 3

    def build_context(
        self,
        user_id: str,
        memory_context: Dict,
        metadata: Dict = None
    ) -> str:

        sections = []

        brain_snapshot = memory_context.get(
            "brain_snapshot", {}
        )

        proposals = memory_context.get(
            "proposals", []
        )

        conversations = memory_context.get(
            "conversations", []
        )

        clients = memory_context.get(
            "clients", []
        )

        # Build structured sections
        sections.append(
            self._build_identity_section(brain_snapshot)
        )

        sections.append(
            self._build_voice_section(brain_snapshot)
        )

        sections.append(
            self._build_skills_section(brain_snapshot)
        )

        sections.append(
            self._build_proposals_section(proposals)
        )

        sections.append(
            self._build_conversations_section(conversations)
        )

        sections.append(
            self._build_clients_section(clients)
        )

        if metadata:
            sections.append(
                self._build_metadata_section(metadata)
            )

        context = "\n\n".join([
            section for section in sections
            if section
        ])

        return f"BRAIN CONTEXT:\n\n{context}"

    def _build_identity_section(
        self,
        brain: Dict
    ) -> str:

        authority = brain.get(
            "authority_level",
            "Developing"
        )

        niches = brain.get(
            "niches",
            []
        )

        return f"""
FREELANCER PROFILE:

Authority Level: {authority}

Primary Niches: {", ".join(niches)}
""".strip()

    def _build_voice_section(
        self,
        brain: Dict
    ) -> str:

        voice = brain.get(
            "voice_profile",
            {}
        )

        tone = voice.get(
            "tone",
            "confident"
        )

        style = voice.get(
            "style",
            "concise, direct"
        )

        return f"""
VOICE PROFILE:

Tone: {tone}

Style: {style}

Instruction: Always match this voice profile when generating responses.
""".strip()

    def _build_skills_section(
        self,
        brain: Dict
    ) -> str:

        skills = brain.get(
            "skills",
            []
        )

        if not skills:
            return ""

        return f"""
CORE SKILLS:

{", ".join(skills)}
""".strip()

    def _build_proposals_section(
        self,
        proposals: List[Dict]
    ) -> str:

        if not proposals:
            return ""

        section = "RELEVANT PAST PROPOSALS:\n"

        for proposal in proposals[:self.max_proposals]:

            if isinstance(proposal, dict):

                summary = proposal.get(
                    "content",
                    ""
                )[:300]

                section += f"\n{summary}\n"

        return section.strip()

    def _build_conversations_section(
        self,
        conversations: List[Dict]
    ) -> str:

        if not conversations:
            return ""

        section = "RELEVANT CONVERSATION HISTORY:\n"

        for convo in conversations[:self.max_conversations]:

            if isinstance(convo, dict):

                summary = convo.get(
                    "summary",
                    ""
                )[:300]

                section += f"\n{summary}\n"

        return section.strip()

    def _build_clients_section(
        self,
        clients: List[Dict]
    ) -> str:

        if not clients:
            return ""

        section = "CLIENT INTELLIGENCE:\n"

        for client in clients[:self.max_clients]:

            if isinstance(client, dict):

                name = client.get("name", "Unknown")

                stats = client.get(
                    "stats", {}
                )

                section += f"""
Client: {name}

Hire Rate: {stats.get('hire_rate','unknown')}

Total Spent: {stats.get('total_spent','unknown')}
"""

        return section.strip()

    def _build_metadata_section(
        self,
        metadata: Dict
    ) -> str:

        return f"""
SESSION METADATA:

{json.dumps(metadata, indent=2)}
""".strip()
