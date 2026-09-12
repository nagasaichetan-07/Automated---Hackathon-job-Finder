"""
Aegis — Deterministic Eligibility Engine

Evaluates student profiles against opportunities using strict deterministic rules (AC-3.1).
Guarantees:
1. No LLM calls in the critical disqualification path.
2. Mandatory Tri-State output: ELIGIBLE, INELIGIBLE, or UNKNOWN (AC-3.2).
3. UNKNOWN is preserved when evidence is insufficient — never guessed (AC-3.3).
4. Hard exclusions dominate: any rule failure immediately causes INELIGIBLE (AC-3.4).
5. Comprehensive rule audit trail with supporting evidence snippets (§2.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core.schemas.domain import (
    EligibilityDecisionSchema,
    EligibilityState,
    OpportunitySchema,
    ProfileSchema,
)


@dataclass
class RuleVerdict:
    """Outcome of a single eligibility rule evaluation."""

    rule_name: str
    status: str  # "PASS", "FAIL", "UNKNOWN"
    reason: str
    evidence: str
    confidence: float = 1.0


class EligibilityEngine:
    """Deterministic eligibility rule engine."""

    def evaluate(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
        current_time: datetime | None = None,
    ) -> EligibilityDecisionSchema:
        """
        Evaluate eligibility of a profile for an opportunity.
        Returns an EligibilityDecisionSchema with state, evidence, and rule_results.
        """
        now = current_time or datetime.now(UTC)
        verdicts: list[RuleVerdict] = [
            self._evaluate_deadline(profile, opportunity, now),
            self._evaluate_degree(profile, opportunity),
            self._evaluate_graduation_year(profile, opportunity),
            self._evaluate_branch(profile, opportunity),
            self._evaluate_location(profile, opportunity),
            self._evaluate_team_size(profile, opportunity),
        ]

        rule_results: dict[str, Any] = {}
        evidence: dict[str, str] = {}
        has_failure = False
        has_pass = False
        all_unknown = True

        for v in verdicts:
            rule_results[v.rule_name] = {
                "status": v.status,
                "reason": v.reason,
                "confidence": v.confidence,
            }
            if v.evidence:
                evidence[v.rule_name] = v.evidence

            if v.status == "FAIL":
                has_failure = True
                all_unknown = False
            elif v.status == "PASS":
                has_pass = True
                all_unknown = False

        # Tri-State Resolution:
        # 1. Hard exclusions dominate: any failure -> INELIGIBLE
        # 2. Insufficient evidence: if no failures and no explicit passes, or all unknown -> UNKNOWN
        # 3. If explicit criteria exist and passed with no failures -> ELIGIBLE
        if has_failure:
            overall_state = EligibilityState.INELIGIBLE
            confidence = 1.0
        elif all_unknown:
            overall_state = EligibilityState.UNKNOWN
            confidence = 0.5
        elif has_pass:
            # Check if any crucial rule was UNKNOWN because profile data was missing
            # If opportunity had an explicit requirement that couldn't be verified -> UNKNOWN
            needs_clarification = False
            for v in verdicts:
                if v.status == "UNKNOWN" and "missing profile" in v.reason.lower():
                    needs_clarification = True
                    break

            if needs_clarification:
                overall_state = EligibilityState.UNKNOWN
                confidence = 0.6
            else:
                overall_state = EligibilityState.ELIGIBLE
                confidence = 0.95
        else:
            overall_state = EligibilityState.UNKNOWN
            confidence = 0.5

        import uuid
        return EligibilityDecisionSchema(
            id=uuid.uuid4(),
            opportunity_id=opportunity.id,
            profile_id=profile.id,
            state=overall_state,
            evidence=evidence,
            rule_results=rule_results,
            confidence=confidence,
            evaluated_at=now,
        )

    # -----------------------------------------------------------------------
    # Rule 1: Registration Deadline
    # -----------------------------------------------------------------------
    def _evaluate_deadline(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
        now: datetime,
    ) -> RuleVerdict:
        """Rule evaluating whether opportunity registration is still open."""
        deadline = opportunity.registration_deadline
        if deadline is None:
            return RuleVerdict(
                rule_name="deadline",
                status="UNKNOWN",
                reason="No registration deadline specified in opportunity.",
                evidence="",
                confidence=0.5,
            )

        # Ensure deadline is timezone-aware for comparison
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)

        deadline_str = deadline.strftime("%Y-%m-%d %H:%M UTC")
        if deadline < now:
            return RuleVerdict(
                rule_name="deadline",
                status="FAIL",
                reason=f"Registration deadline expired on {deadline_str}.",
                evidence=f"Deadline: {deadline_str} (Evaluated at: {now.strftime('%Y-%m-%d')})",
                confidence=1.0,
            )

        return RuleVerdict(
            rule_name="deadline",
            status="PASS",
            reason=f"Registration is active until {deadline_str}.",
            evidence=f"Deadline: {deadline_str}",
            confidence=1.0,
        )

    # -----------------------------------------------------------------------
    # Rule 2: Degree / Education Level
    # -----------------------------------------------------------------------
    def _evaluate_degree(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
    ) -> RuleVerdict:
        """Rule evaluating education degree constraints."""
        text = self._get_combined_opportunity_text(opportunity)
        if not text:
            return RuleVerdict(
                rule_name="degree",
                status="UNKNOWN",
                reason="No opportunity description or eligibility text available.",
                evidence="",
            )

        # Detect degree requirements in opportunity
        req_phd = bool(re.search(r"\b(ph\.?d|doctorate)\b", text, re.IGNORECASE))
        req_masters = bool(re.search(r"\b(master'?s?|m\.?tech|m\.?s|msc|mba)\b", text, re.IGNORECASE))
        req_bachelors = bool(re.search(r"\b(bachelor'?s?|b\.?tech|b\.?e|bsc|undergrad(?:uate)?)\b", text, re.IGNORECASE))

        if not (req_phd or req_masters or req_bachelors):
            return RuleVerdict(
                rule_name="degree",
                status="UNKNOWN",
                reason="No explicit degree restrictions detected in opportunity text.",
                evidence="",
            )

        # Profile check
        user_edu = (profile.education_level or "").lower().strip()
        if not user_edu:
            return RuleVerdict(
                rule_name="degree",
                status="UNKNOWN",
                reason="Opportunity specifies degree requirements, but missing profile education level.",
                evidence=f"Degree terms in opportunity: {'PhD ' if req_phd else ''}{'Masters ' if req_masters else ''}{'Bachelors' if req_bachelors else ''}",
            )

        user_is_bachelor = any(term in user_edu for term in ("bachelor", "b.tech", "b.e", "undergrad", "btech", "bs", "bsc"))
        user_is_master = any(term in user_edu for term in ("master", "m.tech", "m.s", "grad", "mtech", "ms", "msc", "mba"))
        user_is_phd = any(term in user_edu for term in ("phd", "doctorate"))

        # PhD only requirement
        if req_phd and not (req_masters or req_bachelors):
            if user_is_phd:
                return RuleVerdict(
                    rule_name="degree",
                    status="PASS",
                    reason=f"Matches required PhD level ({profile.education_level}).",
                    evidence="PhD requirement satisfied",
                )
            return RuleVerdict(
                rule_name="degree",
                status="FAIL",
                reason=f"Opportunity requires PhD, but profile education level is {profile.education_level}.",
                evidence="Opportunity text specifies PhD requirement",
            )

        # Masters only requirement
        if req_masters and not req_bachelors:
            if user_is_master or user_is_phd:
                return RuleVerdict(
                    rule_name="degree",
                    status="PASS",
                    reason=f"Matches required graduate/Master's level ({profile.education_level}).",
                    evidence="Graduate/Master's requirement satisfied",
                )
            return RuleVerdict(
                rule_name="degree",
                status="FAIL",
                reason=f"Opportunity requires Master's/Graduate degree, but profile is {profile.education_level}.",
                evidence="Opportunity text specifies Master's requirement",
            )

        # Undergraduate / Bachelor requirement
        if req_bachelors:
            if user_is_bachelor or user_is_master or user_is_phd:
                return RuleVerdict(
                    rule_name="degree",
                    status="PASS",
                    reason=f"Profile education level ({profile.education_level}) satisfies degree criteria.",
                    evidence="Bachelor/Undergraduate requirement satisfied",
                )

        return RuleVerdict(
            rule_name="degree",
            status="UNKNOWN",
            reason=f"Could not conclusively verify education level '{profile.education_level}'.",
            evidence="",
        )

    # -----------------------------------------------------------------------
    # Rule 3: Graduation Year
    # -----------------------------------------------------------------------
    def _evaluate_graduation_year(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
    ) -> RuleVerdict:
        """Rule evaluating graduation year / batch constraints."""
        text = self._get_combined_opportunity_text(opportunity)

        # Look for explicit year mentions like "Batch of 2025", "2025 grads", "2025 or 2026 graduates"
        matches = re.findall(r"\b(?:batch of|graduating in|class of|graduates of|passout of)?\s*(202[4-9]|203[0-5])\b", text, re.IGNORECASE)
        years = {int(m) for m in matches if m.isdigit()}

        if not years:
            return RuleVerdict(
                rule_name="graduation_year",
                status="UNKNOWN",
                reason="No graduation year constraints detected in opportunity.",
                evidence="",
            )

        if profile.graduation_year is None:
            return RuleVerdict(
                rule_name="graduation_year",
                status="UNKNOWN",
                reason=f"Opportunity restricts to graduation year(s) {sorted(years)}, but missing profile graduation year.",
                evidence=f"Opportunity targets: {sorted(years)}",
            )

        if profile.graduation_year in years:
            return RuleVerdict(
                rule_name="graduation_year",
                status="PASS",
                reason=f"Graduation year {profile.graduation_year} matches opportunity target batch {sorted(years)}.",
                evidence=f"Profile graduation year: {profile.graduation_year}",
            )

        return RuleVerdict(
            rule_name="graduation_year",
            status="FAIL",
            reason=f"Graduation year {profile.graduation_year} does not match allowed batches {sorted(years)}.",
            evidence=f"Target batch: {sorted(years)}, Profile year: {profile.graduation_year}",
        )

    # -----------------------------------------------------------------------
    # Rule 4: Branch of Study / Major
    # -----------------------------------------------------------------------
    def _evaluate_branch(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
    ) -> RuleVerdict:
        """Rule evaluating academic branch or major constraints."""
        text = self._get_combined_opportunity_text(opportunity)

        # Check if opportunity restricts to specific branches
        cs_pattern = re.search(r"\b(computer science|cs|it|information technology|software engineering)\s*(?:only|majors?|degrees?)\b", text, re.IGNORECASE)

        if not cs_pattern:
            return RuleVerdict(
                rule_name="branch",
                status="UNKNOWN",
                reason="No explicit branch restrictions detected.",
                evidence="",
            )

        if not profile.branch:
            return RuleVerdict(
                rule_name="branch",
                status="UNKNOWN",
                reason="Opportunity specifies branch restrictions, but missing profile branch.",
                evidence=f"Detected branch requirement: '{cs_pattern.group(0)}'",
            )

        user_branch = profile.branch.lower()
        is_cs = any(b in user_branch for b in ("computer", "cs", "it", "software", "information technology", "data science"))

        if is_cs:
            return RuleVerdict(
                rule_name="branch",
                status="PASS",
                reason=f"Profile branch '{profile.branch}' satisfies branch requirement.",
                evidence=f"Matched '{profile.branch}' against '{cs_pattern.group(0)}'",
            )

        return RuleVerdict(
            rule_name="branch",
            status="FAIL",
            reason=f"Opportunity restricts to CS/IT majors, but profile branch is '{profile.branch}'.",
            evidence=f"Requirement: '{cs_pattern.group(0)}', Profile: '{profile.branch}'",
        )

    # -----------------------------------------------------------------------
    # Rule 5: Location / Mode
    # -----------------------------------------------------------------------
    def _evaluate_location(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
    ) -> RuleVerdict:
        """Rule evaluating location and remote/onsite mode constraints."""
        from core.schemas.domain import OpportunityMode

        if opportunity.mode == OpportunityMode.REMOTE:
            return RuleVerdict(
                rule_name="location",
                status="PASS",
                reason="Opportunity is remote; open to all locations.",
                evidence="Mode: remote",
            )

        if not opportunity.location:
            return RuleVerdict(
                rule_name="location",
                status="UNKNOWN",
                reason="No location specified for opportunity.",
                evidence="",
            )

        if not profile.preferred_locations:
            return RuleVerdict(
                rule_name="location",
                status="UNKNOWN",
                reason=f"Onsite location '{opportunity.location}', but profile has no location preferences.",
                evidence=f"Location: {opportunity.location}",
            )

        # Check if opportunity location overlaps with preferred locations
        opp_loc = opportunity.location.lower()
        matched_loc = None
        for pref in profile.preferred_locations:
            if pref.lower() in opp_loc or opp_loc in pref.lower():
                matched_loc = pref
                break

        if matched_loc:
            return RuleVerdict(
                rule_name="location",
                status="PASS",
                reason=f"Opportunity location '{opportunity.location}' matches preferred location '{matched_loc}'.",
                evidence=f"Location match: {matched_loc}",
            )

        # Strict constraint check
        strict_loc = profile.constraints.get("strict_location", False) if profile.constraints else False
        if strict_loc:
            return RuleVerdict(
                rule_name="location",
                status="FAIL",
                reason=f"Location '{opportunity.location}' does not match strict preferences {profile.preferred_locations}.",
                evidence=f"Location: {opportunity.location}",
            )

        return RuleVerdict(
            rule_name="location",
            status="UNKNOWN",
            reason=f"Onsite location '{opportunity.location}' not in preferred locations, but relocation not strictly barred.",
            evidence=f"Location: {opportunity.location}",
        )

    # -----------------------------------------------------------------------
    # Rule 6: Team Size Limits
    # -----------------------------------------------------------------------
    def _evaluate_team_size(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
    ) -> RuleVerdict:
        """Rule evaluating team size requirements for hackathons/contests."""
        min_size = opportunity.team_size_min
        max_size = opportunity.team_size_max

        if min_size is None and max_size is None:
            return RuleVerdict(
                rule_name="team_size",
                status="UNKNOWN",
                reason="No team size constraints specified.",
                evidence="",
            )

        # Check if user specified individual-only preference in constraints
        solo_only = profile.constraints.get("solo_only", False) if profile.constraints else False
        if solo_only and min_size is not None and min_size > 1:
            return RuleVerdict(
                rule_name="team_size",
                status="FAIL",
                reason=f"Requires minimum team size of {min_size}, but user specified solo participation only.",
                evidence=f"Min team size: {min_size}",
            )

        return RuleVerdict(
            rule_name="team_size",
            status="PASS",
            reason=f"Team size limits ({min_size or 1}-{max_size or 'any'}) are compatible.",
            evidence=f"Team size range: {min_size}-{max_size}",
        )

    def _get_combined_opportunity_text(self, opp: OpportunitySchema) -> str:
        """Combine opportunity text fields for rule pattern matching."""
        parts = []
        if opp.title:
            parts.append(opp.title)
        if opp.description:
            parts.append(opp.description)
        if opp.eligibility_text:
            parts.append(opp.eligibility_text)
        return " ".join(parts)
