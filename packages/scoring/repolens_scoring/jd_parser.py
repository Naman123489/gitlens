"""Job-description parsing.

Deterministic, offline and explainable: the parser segments the description into
sections, extracts canonical skills via the taxonomy, decides whether each skill
is required or preferred from the section it appeared in and the language around
it, and assigns an importance weight.

An LLM may later *enrich* the parse (see ``apps/api/app/services/llm.py``), but
the structured output below is produced without one so the system works with no
model configured.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .taxonomy import SKILLS_BY_KEY, Skill, expand_implications, extract_skills

#: Section headings that mark hard requirements.
_REQUIRED_HEADINGS = re.compile(
    r"(?im)^\s*[#*\-\s]*\b(requirements?|must[- ]haves?|qualifications?|"
    r"required skills?|what you.ll need|minimum qualifications?|essential)\b\s*:?\s*$"
)
_PREFERRED_HEADINGS = re.compile(
    r"(?im)^\s*[#*\-\s]*\b(nice[- ]to[- ]haves?|preferred|bonus|plus(es)?|desirable|"
    r"good to have|preferred qualifications?|optional)\b\s*:?\s*$"
)
_RESPONSIBILITY_HEADINGS = re.compile(
    r"(?im)^\s*[#*\-\s]*\b(responsibilities|what you.ll do|the role|about the role|"
    r"day to day|your impact|duties)\b\s*:?\s*$"
)

_REQUIRED_INLINE = re.compile(r"(?i)\b(must have|required|strong|solid|proven|essential|"
                              r"expert|deep (?:knowledge|experience)|proficien\w+)\b")
_PREFERRED_INLINE = re.compile(r"(?i)\b(nice to have|preferred|bonus|a plus|desirable|"
                               r"familiarity|exposure|some experience|helpful|ideally)\b")

_EXPERIENCE_RE = re.compile(r"(?i)(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years?")
_LEVEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("intern", re.compile(r"(?i)\b(intern|internship|trainee|apprentice)\b")),
    ("entry", re.compile(r"(?i)\b(entry[- ]level|graduate|junior|new grad|fresher|associate)\b")),
    ("senior", re.compile(r"(?i)\b(senior|sr\.?|lead|principal|staff|architect)\b")),
    ("mid", re.compile(r"(?i)\b(mid[- ]level|intermediate|\b[3-5]\+?\s*years)\b")),
)

_DOMAIN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ai_ml", re.compile(r"(?i)\b(machine learning|ml engineer|ai engineer|deep learning|"
                         r"data scien\w+|nlp|llm|generative ai)\b")),
    ("backend", re.compile(r"(?i)\b(backend|back[- ]end|server[- ]side|api engineer|platform engineer)\b")),
    ("frontend", re.compile(r"(?i)\b(frontend|front[- ]end|ui engineer|web developer)\b")),
    ("fullstack", re.compile(r"(?i)\b(full[- ]?stack)\b")),
    ("devops", re.compile(r"(?i)\b(devops|sre|site reliability|platform|infrastructure engineer)\b")),
    ("security", re.compile(r"(?i)\b(security engineer|appsec|application security|cybersecurity)\b")),
    ("mobile", re.compile(r"(?i)\b(mobile engineer|ios engineer|android engineer)\b")),
    ("data", re.compile(r"(?i)\b(data engineer|analytics engineer|etl)\b")),
)


@dataclass(slots=True)
class ParsedRequirement:
    skill: str
    label: str
    dimension: str
    required: bool
    importance: float
    matched_terms: list[str] = field(default_factory=list)
    source: str = "explicit"  # "explicit" | "implied"
    section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParsedJob:
    requirements: list[ParsedRequirement] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    experience_level: str = "unspecified"
    min_years_experience: int | None = None
    domain: str = "general"
    technologies: list[str] = field(default_factory=list)
    unmatched_terms: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def required_skills(self) -> list[ParsedRequirement]:
        return [r for r in self.requirements if r.required]

    def preferred_skills(self) -> list[ParsedRequirement]:
        return [r for r in self.requirements if not r.required]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirements": [r.to_dict() for r in self.requirements],
            "responsibilities": self.responsibilities,
            "experience_level": self.experience_level,
            "min_years_experience": self.min_years_experience,
            "domain": self.domain,
            "technologies": self.technologies,
            "unmatched_terms": self.unmatched_terms,
            "notes": self.notes,
        }


def _segment(text: str) -> list[tuple[str, str]]:
    """Split the description into ``(section_kind, body)`` pairs."""
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = [("general", [])]
    for line in lines:
        if _REQUIRED_HEADINGS.match(line):
            sections.append(("required", []))
        elif _PREFERRED_HEADINGS.match(line):
            sections.append(("preferred", []))
        elif _RESPONSIBILITY_HEADINGS.match(line):
            sections.append(("responsibilities", []))
        else:
            sections[-1][1].append(line)
    return [(kind, "\n".join(body)) for kind, body in sections]


def _detect_level(text: str) -> tuple[str, int | None]:
    years = [int(m.group(1)) for m in _EXPERIENCE_RE.finditer(text)]
    min_years = min(years) if years else None
    for level, pattern in _LEVEL_PATTERNS:
        if pattern.search(text):
            return level, min_years
    if min_years is not None:
        if min_years >= 6:
            return "senior", min_years
        if min_years >= 3:
            return "mid", min_years
        return "entry", min_years
    return "unspecified", min_years


def _detect_domain(text: str) -> str:
    for domain, pattern in _DOMAIN_PATTERNS:
        if pattern.search(text):
            return domain
    return "general"


def _bullets(body: str) -> list[str]:
    items = [
        re.sub(r"^\s*[-*•\d.)\s]+", "", line).strip()
        for line in body.splitlines()
        if line.strip() and re.match(r"^\s*[-*•]|^\s*\d+[.)]", line)
    ]
    if items:
        return [i for i in items if len(i) > 3][:20]
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if len(s.strip()) > 20][:20]


def parse_job_description(text: str, title: str = "") -> ParsedJob:
    """Parse a job description into structured, weighted requirements."""
    combined = f"{title}\n{text}"
    parsed = ParsedJob()
    level, years = _detect_level(combined)
    parsed.experience_level = level
    parsed.min_years_experience = years
    parsed.domain = _detect_domain(combined)

    per_skill: dict[str, ParsedRequirement] = {}

    for kind, body in _segment(text):
        if not body.strip():
            continue
        if kind == "responsibilities":
            parsed.responsibilities.extend(_bullets(body))
        for key, terms in extract_skills(body).items():
            skill = SKILLS_BY_KEY[key]
            required = kind == "required"
            if kind == "general":
                required = bool(_REQUIRED_INLINE.search(body)) and not _PREFERRED_INLINE.search(body)
            elif kind == "preferred":
                required = False
            existing = per_skill.get(key)
            if existing:
                existing.required = existing.required or required
                for term in terms:
                    if term not in existing.matched_terms:
                        existing.matched_terms.append(term)
                continue
            per_skill[key] = ParsedRequirement(
                skill=key, label=skill.label, dimension=str(skill.dimension),
                required=required, importance=0.0, matched_terms=list(terms),
                section=kind,
            )

    # Also scan the title, which frequently names the core technology.
    for key, terms in extract_skills(title).items():
        if key in per_skill:
            per_skill[key].required = True
        else:
            skill = SKILLS_BY_KEY[key]
            per_skill[key] = ParsedRequirement(
                skill=key, label=skill.label, dimension=str(skill.dimension),
                required=True, importance=0.0, matched_terms=list(terms), section="title",
            )

    # Implied skills are added as low-weight preferred requirements so that a job
    # asking for "PyTorch" still credits Python evidence.
    explicit = set(per_skill)
    for key in expand_implications(explicit) - explicit:
        skill: Skill = SKILLS_BY_KEY[key]
        per_skill[key] = ParsedRequirement(
            skill=key, label=skill.label, dimension=str(skill.dimension),
            required=False, importance=0.0, matched_terms=[], source="implied",
        )

    _assign_importance(list(per_skill.values()), title)
    parsed.requirements = sorted(per_skill.values(), key=lambda r: (-r.importance, r.label))
    parsed.technologies = [r.label for r in parsed.requirements if r.source == "explicit"]

    if not parsed.requirements:
        parsed.notes.append(
            "No skills from the RepoLens taxonomy were recognised in this description. "
            "Add requirements manually so evaluations can be matched against them."
        )
    if not parsed.responsibilities:
        parsed.responsibilities = _bullets(text)[:8]
    return parsed


def _assign_importance(requirements: list[ParsedRequirement], title: str) -> None:
    """Normalise importance weights across the requirement set (they sum to 1).

    Base weight comes from required/preferred and from how often the skill was
    mentioned; a title mention doubles it, because the job title is the single
    strongest statement of what the role is.
    """
    title_lower = title.lower()
    raw: list[float] = []
    for requirement in requirements:
        base = 1.0 if requirement.required else 0.45
        if requirement.source == "implied":
            base = 0.2
        base *= 1.0 + 0.15 * math.log1p(max(0, len(requirement.matched_terms) - 1))
        if any(term.lower() in title_lower for term in requirement.matched_terms):
            base *= 2.0
        raw.append(base)
    total = sum(raw) or 1.0
    for requirement, value in zip(requirements, raw):
        requirement.importance = round(value / total, 4)
