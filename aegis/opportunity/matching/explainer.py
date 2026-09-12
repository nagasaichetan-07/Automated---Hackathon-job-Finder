"""
Aegis — Fact-Grounded Explanation Generator

Produces transparent, plain-language match explanations grounded strictly in stored facts
(AC-3.7, §2.4). Never hallucinates or invents reasons not found in the profile or opportunity records.
"""

from __future__ import annotations

from typing import Any

from core.schemas.domain import (
    EligibilityDecisionSchema,
    EligibilityState,
    OpportunitySchema,
    ProfileSchema,
)


class MatchExplainer:
    """Fact-grounded explanation generator for matched opportunities."""

    def generate_explanation(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
        eligibility: EligibilityDecisionSchema,
        feature_breakdown: dict[str, Any],
        semantic_score: float,
    ) -> str:
        """
        Generate plain-language explanation citing real profile and opportunity facts.
        """
        points: list[str] = []

        # 1. Eligibility Fact
        if eligibility.state == EligibilityState.INELIGIBLE:
            # Find the failure reason
            fail_reasons: list[str] = []
            for rule_name, details in eligibility.rule_results.items():
                if isinstance(details, dict) and details.get("status") == "FAIL":
                    fail_reasons.append(details.get("reason", f"{rule_name} rule failed"))

            if fail_reasons:
                points.append(f"Ineligible: {'; '.join(fail_reasons)}.")
            else:
                points.append("Ineligible: Hard qualification constraints were not satisfied.")
            return " ".join(points)

        elif eligibility.state == EligibilityState.ELIGIBLE:
            pass_notes: list[str] = []
            for rule_name, details in eligibility.rule_results.items():
                if isinstance(details, dict) and details.get("status") == "PASS":
                    pass_notes.append(details.get("reason", f"{rule_name} satisfied"))
            if pass_notes:
                # Use top 2 pass notes
                points.append(f"Eligible: {'; '.join(pass_notes[:2])}.")
            else:
                points.append("Eligible: Meets all specified qualification requirements.")

        else:  # UNKNOWN
            unknown_rules: list[str] = []
            for rule_name, details in eligibility.rule_results.items():
                if isinstance(details, dict) and details.get("status") == "UNKNOWN" and details.get("reason"):
                    unknown_rules.append(rule_name)
            if unknown_rules:
                points.append(f"Eligibility pending confirmation: insufficient data for {', '.join(unknown_rules)}.")
            else:
                points.append("Eligibility unconfirmed: opportunity does not specify complete criteria.")

        # 2. Skill Overlap Fact
        skill_info = feature_breakdown.get("skill_overlap", {})
        matched_skills = skill_info.get("matched_skills", [])
        if matched_skills:
            points.append(f"Matches your confirmed skills in {', '.join(matched_skills[:5])}.")

        # 3. Location / Mode Fact
        loc_info = feature_breakdown.get("location_compatibility", {})
        if loc_info.get("mode") == "remote":
            points.append("Offers remote participation.")
        elif loc_info.get("opportunity_location"):
            points.append(f"Located in {loc_info['opportunity_location']}.")

        # 4. Semantic alignment note if strong
        if semantic_score >= 0.70:
            points.append("Strong semantic match with your profile interests and background.")

        # 5. Deadline notice if active
        if opportunity.registration_deadline:
            deadline_fmt = opportunity.registration_deadline.strftime("%b %d, %Y")
            points.append(f"Registration deadline: {deadline_fmt}.")

        return " ".join(points)
