"""
Aegis — Structured Feature Overlap Engine

Calculates deterministic structured feature overlap between student profiles and opportunities:
- Skill overlap (Jaccard / intersection over required skills)
- Category / opportunity type alignment
- Location & participation mode compatibility
"""

from __future__ import annotations

from typing import Any

from core.schemas.domain import (
    OpportunityCategory,
    OpportunityMode,
    OpportunitySchema,
    ProfileSchema,
)


def calculate_skill_overlap(
    profile_skills: list[str],
    opportunity_skills: list[str],
    opportunity_text: str = "",
) -> tuple[float, list[str], list[str]]:
    """
    Calculate skill alignment between profile and opportunity.

    Returns:
        (overlap_score, matched_skills, missing_skills)
    """
    if not profile_skills:
        return 0.0, [], opportunity_skills

    norm_profile_skills = {s.lower().strip() for s in profile_skills if s and s.strip()}
    norm_opp_skills = {s.lower().strip() for s in opportunity_skills if s and s.strip()}

    # Also search for profile skills mentioned in opportunity text if opp skills list is small
    text_lower = opportunity_text.lower()
    matched: set[str] = set()
    missing: set[str] = set()

    if norm_opp_skills:
        for opp_skill in norm_opp_skills:
            if opp_skill in norm_profile_skills:
                matched.add(opp_skill)
            else:
                missing.add(opp_skill)

        # In addition, check if any profile skill is present in opp text
        for p_skill in norm_profile_skills:
            if p_skill in text_lower and p_skill not in matched:
                matched.add(p_skill)

        # Denominator is total unique skills referenced
        total_skills = len(norm_opp_skills | matched)
        score = len(matched) / total_skills if total_skills > 0 else 0.0
    else:
        # Opportunity has no explicit skill tags — match profile skills in text
        for p_skill in norm_profile_skills:
            # Word boundary check for short skills
            if len(p_skill) <= 3:
                import re
                if re.search(rf"\b{re.escape(p_skill)}\b", text_lower):
                    matched.add(p_skill)
            elif p_skill in text_lower:
                matched.add(p_skill)

        # Baseline score: proportional to matching profile skills capped at 1.0
        score = min(1.0, len(matched) / max(3, len(norm_profile_skills)))

    return round(score, 4), sorted(matched), sorted(missing)


def calculate_location_overlap(
    preferred_locations: list[str],
    opportunity_location: str | None,
    mode: OpportunityMode | None,
) -> float:
    """
    Calculate location and participation mode alignment score [0.0, 1.0].
    """
    if mode == OpportunityMode.REMOTE:
        return 1.0

    if not opportunity_location:
        return 0.5  # Neutral when location is unspecified

    if not preferred_locations:
        return 0.5  # Neutral when user has no geographic restrictions

    opp_loc = opportunity_location.lower()
    for pref in preferred_locations:
        p = pref.lower()
        if p in opp_loc or opp_loc in p:
            return 1.0

    return 0.2  # Low score for non-matching onsite locations


def calculate_category_overlap(
    preferred_types: list[OpportunityCategory],
    opportunity_category: OpportunityCategory,
) -> float:
    """
    Calculate opportunity type alignment score [0.0, 1.0].
    """
    if not preferred_types:
        return 0.8  # High neutral when user is open to all opportunity types

    if opportunity_category in preferred_types:
        return 1.0

    return 0.3  # Penalty for non-preferred opportunity type


def calculate_feature_overlap(
    profile: ProfileSchema,
    opportunity: OpportunitySchema,
) -> tuple[float, dict[str, Any]]:
    """
    Calculate composite structured feature overlap between Profile and Opportunity.

    Returns:
        (composite_score, details_dict)
    """
    opp_text = f"{opportunity.title} {opportunity.description or ''} {opportunity.eligibility_text or ''}"
    skill_score, matched_skills, missing_skills = calculate_skill_overlap(
        profile_skills=profile.skills,
        opportunity_skills=opportunity.skills_themes,
        opportunity_text=opp_text,
    )

    location_score = calculate_location_overlap(
        preferred_locations=profile.preferred_locations,
        opportunity_location=opportunity.location,
        mode=opportunity.mode,
    )

    category_score = calculate_category_overlap(
        preferred_types=profile.opportunity_types,
        opportunity_category=opportunity.category,
    )

    # Weights for structured feature overlap
    w_skill = 0.60
    w_location = 0.20
    w_category = 0.20

    composite = (
        w_skill * skill_score +
        w_location * location_score +
        w_category * category_score
    )
    composite = max(0.0, min(1.0, composite))

    details = {
        "composite": round(composite, 4),
        "skill_overlap": {
            "score": skill_score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "weight": w_skill,
        },
        "location_compatibility": {
            "score": location_score,
            "opportunity_location": opportunity.location,
            "mode": opportunity.mode.value if opportunity.mode else None,
            "weight": w_location,
        },
        "category_alignment": {
            "score": category_score,
            "opportunity_category": opportunity.category.value,
            "weight": w_category,
        },
    }

    return round(composite, 4), details
