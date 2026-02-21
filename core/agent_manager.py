from agents.proposal_agent import ProposalAgent
from agents.conversation_agent import ConversationAgent

class AgentManager:
    def __init__(self):
        self.agents = {
            "proposal_agent": ProposalAgent(),
            "conversation_agent": ConversationAgent(),
        }

    def get_agent(self, agent_name):
        return self.agents.get(agent_name)
