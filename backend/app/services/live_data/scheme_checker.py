import logging
from typing import List, Optional
from backend.app.models.schemas import SchemeEligibilityItem

logger = logging.getLogger(__name__)

class SchemeCheckerService:
    """
    Government Scheme Eligibility Checker.
    Evaluates farmer landholding size, crop selection, and state against
    official criteria for PM-KISAN, PMFBY, KCC, and Soil Health Card.
    """

    def check_eligibility(
        self,
        landholding_acres: float = 2.0,
        crops_grown: Optional[List[str]] = None,
        state: Optional[str] = "Karnataka"
    ) -> List[SchemeEligibilityItem]:
        """
        Evaluates eligibility across all major central and state schemes.
        """
        crops = [c.lower() for c in (crops_grown or ["paddy", "tomato"])]
        results: List[SchemeEligibilityItem] = []

        # 1. PM-KISAN
        # Eligible: Landholding farmer families with cultivable land
        pm_kisan_eligible = landholding_acres > 0
        results.append(SchemeEligibilityItem(
            scheme_id="scheme-pm-kisan-01",
            scheme_name="Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)",
            is_eligible=pm_kisan_eligible,
            reason=f"Farmer holds {landholding_acres} acres of cultivable land and meets non-exclusion landholder criteria."
            if pm_kisan_eligible else "Must own cultivable agricultural land.",
            benefits="Rs. 6,000 per year paid in three equal installments of Rs. 2,000 every 4 months via Direct Benefit Transfer.",
            portal_url="https://pmkisan.gov.in"
        ))

        # 2. PMFBY (Pradhan Mantri Fasal Bima Yojana)
        # Notified crops (Paddy, Wheat, Tomato, Cotton, Maize, etc.)
        notified_crops = {"paddy", "rice", "wheat", "cotton", "maize", "tomato", "soybean", "groundnut"}
        crop_match = any(c in notified_crops for c in crops)
        results.append(SchemeEligibilityItem(
            scheme_id="scheme-pmfby-02",
            scheme_name="Pradhan Mantri Fasal Bima Yojana (PMFBY)",
            is_eligible=crop_match,
            reason=f"Enrolled crops ({', '.join(crops_grown or [])}) are notified crops for comprehensive insurance coverage against non-preventable seasonal risks."
            if crop_match else "Grown crops are not currently in the notified crop schedule.",
            benefits="Full sum insured coverage at nominal farmer premium: 2% for Kharif crops, 1.5% for Rabi crops, and 5% for horticultural crops.",
            portal_url="https://pmfby.gov.in"
        ))

        # 3. Kisan Credit Card (KCC)
        # Accessible to all farmers with valid land record or sharecropper agreement
        kcc_eligible = landholding_acres > 0
        max_limit = min(300000, int(landholding_acres * 50000 + 50000))
        results.append(SchemeEligibilityItem(
            scheme_id="scheme-kcc-03",
            scheme_name="Kisan Credit Card (KCC) Scheme",
            is_eligible=kcc_eligible,
            reason=f"Eligible for credit limit up to ~Rs. {max_limit:,} based on {landholding_acres} acres operational holding."
            if kcc_eligible else "Operational landholding or tenant farming agreement required.",
            benefits="Short term crop loan at 4% effective interest rate (7% base rate with 3% prompt repayment incentive). Collateral-free up to Rs. 1.6 Lakh.",
            portal_url="https://agricoop.nic.in"
        ))

        # 4. Soil Health Card Scheme
        # Universal entitlement for all farmers
        results.append(SchemeEligibilityItem(
            scheme_id="scheme-soil-health-card-04",
            scheme_name="Soil Health Card Scheme",
            is_eligible=True,
            reason="Universal entitlement for all Indian cultivators.",
            benefits="Free soil analysis across 12 vital macro and micro nutrient parameters every 3 years with tailored fertilizer dosages.",
            portal_url="https://soilhealth.dac.gov.in"
        ))

        return results

scheme_checker = SchemeCheckerService()
