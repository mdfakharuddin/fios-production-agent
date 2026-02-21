import asyncio
import json
import time
from typing import Dict, Any, List, Optional

from core.prompt_loader import PromptLoader
from core.context_builder import ContextBuilder
from core.memory_retriever import MemoryRetriever
from core.strategy_engine import StrategyEngine
from core.response_refiner import ResponseRefiner
from core.agent_manager import AgentManager

from core.openrouter_client import OpenRouterClient


class Orchestrator:
    """
    FIOS Central Intelligence Orchestrator

    Responsibilities:

    - Load Master Prompt
    - Retrieve brain memory
    - Build context
    - Select strategy
    - Route to proper agent
    - Execute LLM calls
    - Refine response
    - Return optimized output
    """

    def __init__(self):

        # Core components
        self.prompt_loader = PromptLoader()
        self.context_builder = ContextBuilder()
        self.memory_retriever = MemoryRetriever()
        self.strategy_engine = StrategyEngine()
        self.response_refiner = ResponseRefiner()
        self.agent_manager = AgentManager()

        # LLM client
        self.llm = OpenRouterClient()

        # Cache
        self.master_prompt_cache = None
        self.master_prompt_loaded_at = 0

        # Settings
        self.prompt_cache_ttl = 300  # seconds

    async def process_user_input(
        self,
        user_input: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:

        start_time = time.time()

        # STEP 1: Load Master Prompt
        master_prompt = self._load_master_prompt()

        # STEP 2: Retrieve Memory Context
        memory_context = await self.memory_retriever.retrieve_relevant_context(
            user_id=user_id,
            query=user_input,
            conversation_id=conversation_id
        )

        # STEP 3: Build Brain Context
        brain_context = self.context_builder.build_context(
            user_id=user_id,
            memory_context=memory_context,
            metadata=metadata
        )

        # STEP 4: Determine Strategy
        strategy = await self.strategy_engine.determine_strategy(
            user_input=user_input,
            memory_context=memory_context,
            brain_context=brain_context
        )

        # STEP 5: Select Agent
        agent = self.agent_manager.get_agent(strategy["agent"])

        # STEP 6: Build LLM Messages
        messages = self._build_messages(
            master_prompt,
            brain_context,
            strategy,
            user_input
        )

        # STEP 7: Initial LLM Execution
        raw_response = await self.llm.chat(messages)

        # STEP 8: Agent Post-processing
        agent_response = await agent.process_response(
            raw_response=raw_response,
            strategy=strategy,
            memory_context=memory_context
        )

        # STEP 9: Response Refinement
        final_response = await self.response_refiner.refine(
            response=agent_response,
            strategy=strategy,
            brain_context=brain_context
        )

        # STEP 10: Score Proposal specifically if it was a proposal
        scoring = {}
        if strategy["intent"] == "proposal":
            scoring = self.response_refiner.score_proposal(final_response)

        # STEP 11: Store Memory
        await self.memory_retriever.store_interaction(
            user_id=user_id,
            user_input=user_input,
            response=final_response,
            strategy=strategy,
            conversation_id=conversation_id
        )

        execution_time = time.time() - start_time

        return {
            "response": final_response,
            "strategy": strategy,
            "agent": strategy["agent"],
            "execution_time": execution_time,
            "memory_used": memory_context.get("memory_ids", []),
            "scoring": scoring,
            "status": "success"
        }

    def _load_master_prompt(self) -> str:

        now = time.time()

        if (
            self.master_prompt_cache is None
            or now - self.master_prompt_loaded_at > self.prompt_cache_ttl
        ):

            self.master_prompt_cache = self.prompt_loader.load_master_prompt()

            self.master_prompt_loaded_at = now

        return self.master_prompt_cache

    def _build_messages(
        self,
        master_prompt: str,
        brain_context: str,
        strategy: Dict,
        user_input: str
    ) -> List[Dict]:

        messages = []

        # System Layer 1: Master Prompt
        messages.append({
            "role": "system",
            "content": master_prompt
        })

        # System Layer 2: Brain Context
        messages.append({
            "role": "system",
            "content": brain_context
        })

        # System Layer 3: Strategy Instruction
        messages.append({
            "role": "system",
            "content": f"""
ACTIVE AGENT: {strategy['agent']}

OBJECTIVE:
{strategy['objective']}

RESPONSE MODE:
{strategy['mode']}

PRIORITY:
{strategy['priority']}
"""
        })

        # User input
        messages.append({
            "role": "user",
            "content": user_input
        })

        return messages

    async def background_learning_cycle(self, user_id: str):

        """
        Periodic background intelligence refinement
        """

        memory = await self.memory_retriever.retrieve_recent_interactions(user_id)

        insights = await self.strategy_engine.extract_learning_insights(memory)

        await self.memory_retriever.store_insights(user_id, insights)

    async def autonomous_followup_cycle(self, user_id: str):

        """
        Detect follow-up opportunities automatically
        """

        conversations = await self.memory_retriever.get_active_conversations(user_id)

        opportunities = await self.strategy_engine.detect_followups(conversations)

        return opportunities


# Singleton instance
orchestrator = Orchestrator()
