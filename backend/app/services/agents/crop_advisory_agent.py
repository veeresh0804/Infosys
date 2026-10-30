from backend.app.services.agents.base_rag_agent import BaseRAGAdvisoryAgent


class CropAdvisoryAgent(BaseRAGAdvisoryAgent):
    """
    Specialized Sub-Agent for Crop Advisory.
    Retrieves ICAR package of practices and generates tailored agronomic advice.
    """

    sub_agent_name = "crop_advisory"


crop_advisory_agent = CropAdvisoryAgent()
