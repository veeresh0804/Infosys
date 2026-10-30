from backend.app.services.agents.base_rag_agent import BaseRAGAdvisoryAgent


class PestControlAgent(BaseRAGAdvisoryAgent):
    """
    Specialized Sub-Agent for Pest & Disease Control.
    Retrieves Kisan Call Centre (KCC) and ICAR IPM advisories.
    """

    sub_agent_name = "pest_control"


pest_control_agent = PestControlAgent()
