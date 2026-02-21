from typing import Dict, Any, List
import json


class ProposalAgent:
    """
    FIOS Proposal Optimization Agent

    Responsibilities:

    - Generate high-conversion proposals
    - Use memory context
    - Apply freelancer voice profile
    - Reference past winning proposals
    - Optimize for authority and trust
    """

    def __init__(self):
        self.agent_name = "proposal_agent"

    async def process_response(
        self,
        raw_response: str,
        strategy: Dict,
        memory_context: Dict
    ) -> str:
        enhanced = self._enhance_with_memory(
            raw_response,
            memory_context
        )

        enhanced = self._apply_voice_profile(
            enhanced,
            memory_context
        )

        enhanced = self._optimize_structure(
            enhanced
        )

        return enhanced

    def build_proposal_context(
        self,
        job_data: Dict,
        memory_context: Dict
    ) -> str:
        context_parts = []

        context_parts.append(
            f"JOB TITLE: {job_data.get('title','')}"
        )

        context_parts.append(
            f"JOB DESCRIPTION: {job_data.get('description','')}"
        )

        context_parts.append(
            f"CLIENT NAME: {job_data.get('client_name','')}"
        )

        winning_patterns = self._extract_winning_patterns(
            memory_context
        )

        if winning_patterns:
            context_parts.append(
                "RELEVANT WINNING PROPOSAL PATTERNS:"
            )
            context_parts.extend(winning_patterns)

        return "\n\n".join(context_parts)

    def _enhance_with_memory(
        self,
        proposal: str,
        memory_context: Dict
    ) -> str:
        proposals = memory_context.get(
            "proposals",
            []
        )

        if not proposals:
            return proposal

        relevant = proposals[:2]

        enhancement = "\n".join([
            f"Relevant past success: {p.get('summary','')}"
            for p in relevant
            if isinstance(p, dict)
        ])

        if enhancement.strip():
            return f"{proposal}\n\n{enhancement}"
        return proposal

    def _apply_voice_profile(
        self,
        proposal: str,
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
            proposal = proposal.replace(
                "I think",
                "I recommend"
            )
            proposal = proposal.replace(
                "I can try",
                "I will"
            )

        return proposal

    def _optimize_structure(
        self,
        proposal: str
    ) -> str:
        sections = proposal.split("\n")
        cleaned = []

        for section in sections:
            section = section.strip()

            if not section:
                continue

            cleaned.append(section)

        return "\n\n".join(cleaned)

    def _extract_winning_patterns(
        self,
        memory_context: Dict
    ) -> List[str]:
        proposals = memory_context.get(
            "proposals",
            []
        )
        winning = []

        for proposal in proposals:
            if isinstance(proposal, dict):
                if proposal.get("status") == "won":
                    winning.append(
                        proposal.get("content","")[:300]
                    )

        return winning[:3]
