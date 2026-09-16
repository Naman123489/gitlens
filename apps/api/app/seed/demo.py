"""Development seed data.

Everything created here is marked ``is_demo=True`` and uses the reserved
``@repolens.invalid`` domain, so demo records can always be told apart from real
ones and removed in a single pass.

The seed deliberately does **not** fabricate analyses, scores or evidence.
Creating a fake evaluation would violate the rule that every score is traceable
to real analysis of real code. Instead it creates the accounts, organization,
candidates, jobs and policies, and points at public repositories that a
developer can import and analyse for real in a few seconds.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models import (
    Candidate,
    Job,
    Organization,
    OrganizationMember,
    Repository,
    User,
)
from app.services import policies
from app.services.resume import parse_resume

logger = get_logger("repolens.seed")

DEMO_DOMAIN = "repolens.invalid"
DEMO_PASSWORD = "DemoPassw0rd!2026"


@dataclass(frozen=True, slots=True)
class DemoCandidate:
    name: str
    email: str
    github_login: str
    headline: str
    resume: str
    repositories: tuple[tuple[str, str], ...]  # (full_name, clone_url)


DEMO_CANDIDATES: tuple[DemoCandidate, ...] = (
    DemoCandidate(
        name="Alex Mehta",
        email=f"alex.mehta@{DEMO_DOMAIN}",
        github_login="alexmehta-demo",
        headline="Final-year CS student · backend and ML",
        resume="""Alex Mehta

Skills:
- Python (Advanced), FastAPI (Advanced), PostgreSQL
- PyTorch (Familiar), Docker
- Testing, Git

Projects:
- Document retrieval service built on FastAPI and pgvector
- Coursework compiler written in C

Experience:
Backend Engineering Intern, Northwind (Jun 2025 - Sep 2025)
""",
        repositories=(
            ("pallets/flask", "https://github.com/pallets/flask.git"),
            ("psf/requests", "https://github.com/psf/requests.git"),
        ),
    ),
    DemoCandidate(
        name="Riya Sharma",
        email=f"riya.sharma@{DEMO_DOMAIN}",
        github_login="riyasharma-demo",
        headline="Data science MSc · NLP and evaluation tooling",
        resume="""Riya Sharma

Skills:
- Python (Expert), Machine Learning (Advanced), pandas
- SQL, Data engineering
- Working knowledge of Docker

Projects:
- Text classification benchmark with reproducible evaluation harness
- SQL analytics pipeline over public transit data

Education:
MSc Data Science, 2025
""",
        repositories=(("psf/black", "https://github.com/psf/black.git"),),
    ),
    DemoCandidate(
        name="Dev Patel",
        email=f"dev.patel@{DEMO_DOMAIN}",
        github_login="devpatel-demo",
        headline="Self-taught full-stack developer",
        resume="""Dev Patel

Skills:
- TypeScript, React, Next.js
- Node.js, REST API development
- Familiar with PostgreSQL

Projects:
- Expense tracker with a React frontend and an Express API
- Portfolio site
""",
        repositories=(("sindresorhus/got", "https://github.com/sindresorhus/got.git"),),
    ),
)

DEMO_JOBS: tuple[tuple[str, str], ...] = (
    (
        "AI/ML Engineering Intern",
        """We are looking for an AI/ML engineering intern to join our platform team.

Responsibilities:
- Build retrieval pipelines over our internal document corpus
- Ship FastAPI services that serve model inference
- Write tests and take part in code review

Requirements:
- Strong Python
- PyTorch and machine learning fundamentals
- Experience with RAG and vector databases
- FastAPI, SQL, Git

Nice to have:
- Docker and CI/CD
- React for internal tooling
""",
    ),
    (
        "Backend Engineer (Python)",
        """Backend engineer for our core services team.

Responsibilities:
- Own HTTP APIs end to end, from schema to deployment
- Design data models and write the migrations that get us there
- Keep the service observable and on call for it

Requirements:
- Strong Python
- REST API development
- SQL and PostgreSQL
- Testing and Git
- Docker

Nice to have:
- Redis
- Message queues
- Security engineering
""",
    ),
)


def seed_demo_data(db: Session, reset: bool = False) -> dict[str, int]:
    """Create demo accounts, candidates and jobs. Idempotent."""
    if reset:
        purge_demo_data(db)

    counts = {"users": 0, "candidates": 0, "jobs": 0, "repositories": 0, "policies": 0}

    counts["policies"] = len(policies.ensure_presets(db))

    interviewer = _ensure_user(
        db, email=f"priya.raman@{DEMO_DOMAIN}", name="Priya Raman", role="INTERVIEWER"
    )
    counts["users"] += 1

    organization = (
        db.query(Organization).filter(Organization.slug == "repolens-demo").one_or_none()
    )
    if organization is None:
        organization = Organization(
            name="RepoLens Demo Team", slug="repolens-demo",
            created_by_id=interviewer.id, is_demo=True,
        )
        db.add(organization)
        db.flush()
    if not db.query(OrganizationMember).filter(
        OrganizationMember.organization_id == organization.id,
        OrganizationMember.user_id == interviewer.id,
    ).first():
        db.add(OrganizationMember(
            organization_id=organization.id, user_id=interviewer.id, role="OWNER",
        ))

    for entry in DEMO_CANDIDATES:
        user = _ensure_user(db, email=entry.email, name=entry.name, role="STUDENT")
        counts["users"] += 1

        candidate = (
            db.query(Candidate).filter(Candidate.email == entry.email).one_or_none()
        )
        if candidate is None:
            candidate = Candidate(
                organization_id=organization.id, user_id=user.id, full_name=entry.name,
                email=entry.email, github_login=entry.github_login, headline=entry.headline,
                is_demo=True,
            )
            db.add(candidate)
            db.flush()
            counts["candidates"] += 1

        candidate.resume_text = entry.resume
        candidate.resume_filename = f"{entry.github_login}-resume.md"
        candidate.resume_parsed = parse_resume(entry.resume).to_dict()
        db.add(candidate)

        for full_name, clone_url in entry.repositories:
            exists = (
                db.query(Repository)
                .filter(Repository.owner_user_id == user.id, Repository.full_name == full_name)
                .first()
            )
            if exists:
                continue
            owner, name = full_name.split("/", 1)
            db.add(Repository(
                owner_user_id=user.id, candidate_id=candidate.id, name=name,
                full_name=full_name, clone_url=clone_url,
                html_url=f"https://github.com/{full_name}", default_branch="main",
                description="Demo repository. Run an analysis to produce real scores.",
                is_demo=True, analysis_status="NOT_ANALYZED",
                github_metadata={
                    "metadata_source": "demo_seed",
                    "metadata_note": "Seeded without GitHub API metadata. Analysis produces real "
                                     "results; stars, topics and languages stay empty until the "
                                     "repository is imported through the API.",
                },
            ))
            counts["repositories"] += 1

    for title, description in DEMO_JOBS:
        if db.query(Job).filter(Job.title == title, Job.is_demo.is_(True)).first():
            continue
        job = Job(
            organization_id=organization.id, created_by_id=interviewer.id, title=title,
            description=description, is_public=True, is_demo=True,
        )
        db.add(job)
        db.flush()
        _seed_requirements(db, job)
        counts["jobs"] += 1

    db.flush()
    logger.info("demo_seed_complete", **counts)
    return counts


def _seed_requirements(db: Session, job: Job) -> None:
    from repolens_scoring import parse_job_description

    from app.models import JobRequirement

    parsed = parse_job_description(job.description, title=job.title)
    job.experience_level = parsed.experience_level
    job.min_years_experience = parsed.min_years_experience
    job.domain = parsed.domain
    job.responsibilities = parsed.responsibilities
    job.parse_notes = parsed.notes
    db.add(job)
    for requirement in parsed.requirements:
        db.add(JobRequirement(
            job_id=job.id, skill=requirement.skill, label=requirement.label,
            dimension=requirement.dimension, required=requirement.required,
            importance=requirement.importance, source=requirement.source,
            matched_terms=requirement.matched_terms,
        ))


def _ensure_user(db: Session, email: str, name: str, role: str) -> User:
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is not None:
        return user
    user = User(
        email=email, full_name=name, role=role,
        password_hash=hash_password(DEMO_PASSWORD), is_demo=True,
    )
    db.add(user)
    db.flush()
    return user


def purge_demo_data(db: Session) -> int:
    """Remove every demo record. Real data is never touched."""
    removed = 0
    for model in (Repository, Candidate, Job, Organization, User):
        rows = db.query(model).filter(model.is_demo.is_(True)).all()
        for row in rows:
            db.delete(row)
            removed += 1
    db.flush()
    logger.info("demo_seed_purged", removed=removed)
    return removed
