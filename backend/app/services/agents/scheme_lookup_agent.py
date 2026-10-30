from typing import Dict, Any, Tuple, List
from backend.app.services.live_data.scheme_checker import scheme_checker
from backend.app.services.rag.vector_store import get_vector_store
from backend.app.models.schemas import RetrievedChunk

class SchemeLookupAgent:
    """
    Specialized Sub-Agent for Government Schemes and Subsidies.
    Evaluates farmer eligibility against PM-KISAN, PMFBY, KCC, and Soil Health Card,
    supplemented with knowledge-base scheme retrieval.
    """

    async def execute(
        self,
        query: str,
        farmer_profile: Dict[str, Any]
    ) -> Tuple[str, List[RetrievedChunk], Dict[str, Any]]:
        landholding = farmer_profile.get("landholding_acres", 2.0)
        crops = farmer_profile.get("crops_grown", ["Tomato", "Paddy"])
        state = farmer_profile.get("state", "Karnataka")

        # 1. Evaluate structured eligibility rules
        eligibility_list = scheme_checker.check_eligibility(
            landholding_acres=landholding,
            crops_grown=crops,
            state=state
        )

        # 2. Retrieve scheme details from knowledge base
        vector_store = get_vector_store()
        chunks = await vector_store.similarity_search(query, top_k=2)

        # Build response
        eligible_schemes = [s for s in eligibility_list if s.is_eligible]
        lines = [f"Government Schemes Evaluation for {landholding} acres in {state}:"]
        for s in eligible_schemes[:3]:
            lines.append(f"✓ {s.scheme_name}: Eligible ({s.reason})\n  Benefit: {s.benefits}\n  Portal: {s.portal_url}")

        if chunks:
            lines.append(f"\nAdditional Details ({chunks[0].source}):\n{chunks[0].content[:250]}...")

        answer = "\n\n".join(lines)
        live_data_dict = {
            "schemes_evaluated": [s.model_dump() for s in eligibility_list]
        }
        return answer, chunks, live_data_dict

scheme_lookup_agent = SchemeLookupAgent()
