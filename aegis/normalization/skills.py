"""
Aegis — Skill Normalization & Alias Registry

Normalizes raw skill strings to canonical names using an alias table,
handling synonyms, case variations, and deduplicating skill sets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Canonical alias mapping: lower-cased / cleaned variant -> Canonical Skill Name
SKILL_ALIAS_MAP: dict[str, str] = {
    # JavaScript / TypeScript ecosystem
    "js": "JavaScript",
    "javascript": "JavaScript",
    "java script": "JavaScript",
    "es6": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "type script": "TypeScript",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "next": "Next.js",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "angular": "Angular",
    "angularjs": "Angular",
    # Python ecosystem
    "py": "Python",
    "python": "Python",
    "python3": "Python",
    "fastapi": "FastAPI",
    "fast api": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scipy": "SciPy",
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    # Systems & C-family
    "c": "C",
    "cpp": "C++",
    "c++": "C++",
    "cplusplus": "C++",
    "c#": "C#",
    "csharp": "C#",
    "cs": "C#",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    # Databases
    "sql": "SQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "psql": "PostgreSQL",
    "mysql": "MySQL",
    "my sql": "MySQL",
    "sqlite": "SQLite",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "redis": "Redis",
    # Cloud & DevOps
    "docker": "Docker",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "Google Cloud",
    "google cloud platform": "Google Cloud",
    "azure": "Azure",
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
}


def clean_skill_string(skill: str) -> str:
    """Normalize whitespace and clean punctuation from a raw skill token."""
    # Strip leading/trailing whitespace and symbols like bullets or commas
    cleaned = skill.strip().strip(",;•*-").strip()
    return cleaned


def normalize_skill(skill: str) -> str:
    """
    Resolve a single raw skill name against the canonical alias table.
    If no alias is found, returns the cleaned title-cased or stripped original string.
    """
    cleaned = clean_skill_string(skill)
    if not cleaned:
        return ""

    lookup_key = cleaned.lower()
    if lookup_key in SKILL_ALIAS_MAP:
        return SKILL_ALIAS_MAP[lookup_key]

    # Handle common prefixes/suffixes
    # e.g., "Python 3.x" -> "Python"
    lookup_key_no_version = re.sub(r"\s+v?\d+(\.\d+)*$", "", lookup_key)
    if lookup_key_no_version in SKILL_ALIAS_MAP:
        return SKILL_ALIAS_MAP[lookup_key_no_version]

    # Return title-cased variant if single word, or preserved string
    if " " not in cleaned and not any(c.isupper() for c in cleaned[1:]):
        return cleaned.capitalize()
    return cleaned


def normalize_skills(skills: Iterable[str]) -> list[str]:
    """
    Normalize an iterable of skills, deduplicating them while preserving original order.
    """
    normalized_list: list[str] = []
    seen: set[str] = set()

    for raw in skills:
        canonical = normalize_skill(raw)
        if canonical and canonical.lower() not in seen:
            seen.add(canonical.lower())
            normalized_list.append(canonical)

    return normalized_list
