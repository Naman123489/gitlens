"""Résumé parsing and résumé↔repository consistency.

Extracts skills and claimed proficiency from a résumé and compares them with
repository evidence. The output is deliberately phrased as *verification
recommended*: repository evidence is partial by nature — work done at an
employer, in private repositories or on a whiteboard leaves no trace here — so a
gap is never framed as a false claim.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from repolens_scoring import SKILLS_BY_KEY, extract_skills

#: Proficiency words a résumé may use, mapped to an expected evidence floor.
PROFICIENCY_LEVELS: dict[str, float] = {
    "expert": 0.75, "advanced": 0.65, "proficient": 0.55, "strong": 0.55,
    "experienced": 0.45, "intermediate": 0.35, "working knowledge": 0.3,
    "familiar": 0.2, "basic": 0.15, "beginner": 0.1, "exposure": 0.1,
}

_SECTION_RE = re.compile(
    r"(?im)^\s*(experience|work experience|employment|education|projects?|skills?|"
    r"technical skills|achievements?|certifications?|publications?|internships?)\s*:?\s*$"
)
_BULLET_RE = re.compile(r"^\s*[-*•●▪]\s*")
_DATE_RANGE_RE = re.compile(
    r"(?i)((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}|\d{4})"
    r"\s*[–\-—to]+\s*((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}|\d{4}|present|current)"
)


@dataclass(slots=True)
class ParsedResume:
    skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    projects: list[str] = field(default_factory=list)
    experience_entries: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    achievements: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    word_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills": self.skills, "projects": self.projects,
            "experience_entries": self.experience_entries, "education": self.education,
            "achievements": self.achievements, "sections": self.sections,
            "word_count": self.word_count,
        }


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF. Returns '' when the PDF has no text layer."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:20])
    except Exception:  # noqa: BLE001 - a malformed upload must not 500
        return ""


def _sections(text: str) -> dict[str, list[str]]:
    current = "header"
    buckets: dict[str, list[str]] = {current: []}
    for line in text.splitlines():
        heading = _SECTION_RE.match(line)
        if heading:
            current = heading.group(1).lower()
            buckets.setdefault(current, [])
            continue
        if line.strip():
            buckets[current].append(line.rstrip())
    return buckets


def parse_resume(text: str) -> ParsedResume:
    parsed = ParsedResume(word_count=len(text.split()))
    buckets = _sections(text)
    parsed.sections = sorted(buckets)

    for key, lines in buckets.items():
        body = "\n".join(lines)
        entries = [_BULLET_RE.sub("", l).strip() for l in lines if l.strip()]
        if "project" in key:
            parsed.projects.extend(e for e in entries if len(e) > 8)
        elif "experience" in key or "employment" in key or "internship" in key:
            parsed.experience_entries.extend(e for e in entries if len(e) > 8)
        elif "education" in key:
            parsed.education.extend(e for e in entries if len(e) > 4)
        elif "achievement" in key or "certification" in key or "publication" in key:
            parsed.achievements.extend(e for e in entries if len(e) > 4)

    for skill_key, terms in extract_skills(text).items():
        skill = SKILLS_BY_KEY[skill_key]
        claimed_level, expected = _claimed_level(text, terms)
        parsed.skills[skill_key] = {
            "label": skill.label,
            "dimension": str(skill.dimension),
            "matched_terms": terms,
            "claimed_level": claimed_level,
            "expected_evidence": expected,
            "mentions": sum(text.lower().count(term.lower()) for term in terms),
        }
    return parsed


#: "Python (Advanced)" — a qualifier directly after the skill, on the same line.
#: `[^\S\n]` is "horizontal whitespace": it must not cross a line break, or the
#: next bullet's text would be read as this skill's qualifier.
_QUALIFIER_RE = re.compile(r"^[^\S\n]*[\(\[\-–:][^\S\n]*([a-z ]{3,20})")

_UNKNOWN_EVIDENCE_FLOOR = 0.35


def _claimed_level(text: str, terms: list[str]) -> tuple[str | None, float]:
    """Find the proficiency word a résumé attaches to a skill.

    Attribution is deliberately strict, because skills are usually listed several
    to a line and a loose window assigns one skill's qualifier to its neighbours:

    1. A qualifier immediately following the mention ("Python (Advanced)") wins.
    2. Otherwise a proficiency word elsewhere on the line counts only when that
       line mentions a single skill, so there is no ambiguity about ownership.

    When neither applies the level is unknown and a neutral evidence floor is
    used rather than a guessed level.
    """
    lowered = text.lower()
    found: list[tuple[str, float]] = []

    for term in terms:
        for match in re.finditer(re.escape(term.lower()), lowered):
            qualifier = _QUALIFIER_RE.match(lowered[match.end() : match.end() + 24])
            if qualifier:
                level = _level_in(qualifier.group(1))
                if level:
                    found.append(level)
                    continue
            line_start = lowered.rfind("\n", 0, match.start()) + 1
            line_end = lowered.find("\n", match.end())
            line = lowered[line_start : line_end if line_end != -1 else len(lowered)]
            if _skills_on_line(line) > 1:
                continue
            level = _level_in(line)
            if level:
                found.append(level)

    if not found:
        return None, _UNKNOWN_EVIDENCE_FLOOR
    # Where a résumé states a level more than once, take the strongest claim.
    return max(found, key=lambda item: item[1])


def _level_in(fragment: str) -> tuple[str, float] | None:
    """Longest matching proficiency phrase in ``fragment`` (so "working
    knowledge" is preferred over a bare "knowledge"-adjacent match)."""
    best: tuple[str, float] | None = None
    for level, floor in PROFICIENCY_LEVELS.items():
        if level in fragment and (best is None or len(level) > len(best[0])):
            best = (level, floor)
    return best


def _skills_on_line(line: str) -> int:
    return len(extract_skills(line))


@dataclass(slots=True)
class ConsistencyItem:
    skill: str
    label: str
    claimed_level: str | None
    expected_evidence: float
    observed_evidence: float
    status: str  # "supported" | "partially_supported" | "verification_recommended" | "not_claimed"
    detail: str


def compare_resume_to_evidence(
    parsed: ParsedResume, skill_strengths: dict[str, float]
) -> dict[str, Any]:
    """Compare claimed skills to observed repository evidence."""
    items: list[ConsistencyItem] = []
    for skill_key, claim in parsed.skills.items():
        observed = skill_strengths.get(skill_key, 0.0)
        expected = float(claim["expected_evidence"])
        if observed >= expected:
            status = "supported"
            detail = "Repository evidence is consistent with the résumé claim."
        elif observed >= expected * 0.5:
            status = "partially_supported"
            detail = ("Some repository evidence supports this claim, but less than the stated "
                      "level suggests.")
        else:
            status = "verification_recommended"
            detail = ("No substantial repository evidence was found for this claim. Work done in "
                      "private repositories or at an employer would not appear here, so this is a "
                      "prompt to ask, not a discrepancy.")
        items.append(ConsistencyItem(
            skill=skill_key, label=str(claim["label"]),
            claimed_level=claim.get("claimed_level"), expected_evidence=expected,
            observed_evidence=round(observed, 3), status=status, detail=detail,
        ))

    # Skills evidenced in repositories but absent from the résumé are useful too:
    # candidates routinely undersell themselves.
    unclaimed = [
        {"skill": key, "label": SKILLS_BY_KEY[key].label, "observed_evidence": round(value, 3)}
        for key, value in skill_strengths.items()
        if value >= 0.5 and key not in parsed.skills and key in SKILLS_BY_KEY
    ]

    gaps = [i for i in items if i.status == "verification_recommended"]
    return {
        "items": [
            {
                "skill": i.skill, "label": i.label, "claimed_level": i.claimed_level,
                "expected_evidence": i.expected_evidence, "observed_evidence": i.observed_evidence,
                "status": i.status, "detail": i.detail,
            }
            for i in sorted(items, key=lambda x: (x.status != "verification_recommended", x.label))
        ],
        "unclaimed_strengths": sorted(unclaimed, key=lambda item: -float(item["observed_evidence"]))[:10],
        "supported": sum(1 for i in items if i.status == "supported"),
        "partially_supported": sum(1 for i in items if i.status == "partially_supported"),
        "verification_recommended": len(gaps),
        "claims_total": len(items),
        "limitation": (
            "Repository evidence covers only public and connected repositories analysed by "
            "RepoLens. Absence of evidence is not evidence that a claim is untrue."
        ),
    }
