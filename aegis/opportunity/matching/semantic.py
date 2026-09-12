"""
Aegis — Semantic Matching Engine

Computes semantic text similarity between student profiles and opportunities (AC-3.5).
Provides Sentence Transformers embedding integration (§2.1) with an offline
vectorizer fallback ensuring 100% testability without external model downloads in CI.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from core.schemas.domain import OpportunitySchema, ProfileSchema


def _tokenize_and_vectorize(text: str) -> dict[str, float]:
    """Tokenize text into character n-grams and words, returning normalized frequency vector."""
    if not text:
        return {}

    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    words = [w for w in cleaned.split() if len(w) > 1]

    # Include word unigrams and character trigrams for subword robustness
    features: list[str] = list(words)
    for word in words:
        if len(word) >= 3:
            for i in range(len(word) - 2):
                features.append(word[i:i + 3])

    counts = Counter(features)
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in counts.values()))
    if norm == 0.0:
        return {}
    return {k: v / norm for k, v in counts.items()}


def _cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Compute cosine similarity between two normalized feature vectors."""
    if not vec1 or not vec2:
        return 0.0

    # Dot product of overlapping features
    common = set(vec1.keys()) & set(vec2.keys())
    dot = sum(vec1[k] * vec2[k] for k in common)
    return max(0.0, min(1.0, dot))


class SemanticMatcher:
    """Semantic text matching engine with Sentence Transformers interface."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._st_model: Any = None
        self._st_attempted = False

    def _get_st_model(self) -> Any:
        """Lazy loader for SentenceTransformers model if available."""
        if self._st_attempted:
            return self._st_model

        self._st_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            self._st_model = SentenceTransformer(self.model_name)
        except Exception:
            self._st_model = None
        return self._st_model

    def build_profile_text(self, profile: ProfileSchema) -> str:
        """Build consolidated text representation of user profile."""
        parts: list[str] = []
        if profile.education_level:
            parts.append(profile.education_level)
        if profile.branch:
            parts.append(profile.branch)
        if profile.skills:
            parts.append("Skills: " + ", ".join(profile.skills))
        if profile.interests:
            parts.append("Interests: " + ", ".join(profile.interests))
        if profile.preferred_locations:
            parts.append("Preferred locations: " + ", ".join(profile.preferred_locations))
        return " | ".join(parts)

    def build_opportunity_text(self, opportunity: OpportunitySchema) -> str:
        """Build consolidated text representation of opportunity."""
        parts: list[str] = [opportunity.title]
        if opportunity.category:
            parts.append(f"Type: {opportunity.category.value}")
        if opportunity.description:
            parts.append(opportunity.description)
        if opportunity.skills_themes:
            parts.append("Required skills: " + ", ".join(opportunity.skills_themes))
        if opportunity.location:
            parts.append(f"Location: {opportunity.location}")
        if opportunity.eligibility_text:
            parts.append(opportunity.eligibility_text)
        return " | ".join(parts)

    def compute_similarity(
        self,
        profile: ProfileSchema,
        opportunity: OpportunitySchema,
    ) -> float:
        """
        Compute semantic similarity score between profile and opportunity [0.0, 1.0].
        Uses SentenceTransformers if available, otherwise uses deterministic vectorizer.
        """
        profile_text = self.build_profile_text(profile)
        opp_text = self.build_opportunity_text(opportunity)

        st_model = self._get_st_model()
        if st_model is not None:
            try:
                embeddings = st_model.encode([profile_text, opp_text], normalize_embeddings=True)
                sim = float(embeddings[0] @ embeddings[1])
                return max(0.0, min(1.0, round(sim, 4)))
            except Exception:
                pass

        # Deterministic vectorizer fallback
        vec_p = _tokenize_and_vectorize(profile_text)
        vec_o = _tokenize_and_vectorize(opp_text)
        score = _cosine_similarity(vec_p, vec_o)
        return round(score, 4)
