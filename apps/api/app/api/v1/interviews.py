"""Technical verification: question generation, answers and scoring."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request, status
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, DbSession, user_organization_ids
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.models import (
    Candidate,
    CodeChunk,
    Evaluation,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    Repository,
    RepositoryAnalysis,
    RepositoryFile,
    User,
)
from app.schemas.common import Message
from app.schemas.evaluation import (
    AnswerIn,
    AnswerOut,
    InterviewCreate,
    InterviewOut,
    QuestionOut,
    ReviewerAnswerScore,
)
from app.services import audit, interview

router = APIRouter(prefix="/interviews", tags=["interviews"])


def _visible_session(db: Session, user: User, session_id: str) -> InterviewSession:
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise NotFoundError("Interview session not found.")
    if user.role == "ADMIN" or session.interviewer_id == user.id:
        return session
    if session.organization_id and session.organization_id in user_organization_ids(db, user):
        return session
    if session.candidate_id:
        candidate = db.get(Candidate, session.candidate_id)
        if candidate and candidate.user_id == user.id:
            return session
    raise NotFoundError("Interview session not found.")


def _repository_facts(db: Session, repository_id: str) -> dict:
    """The hard facts an answer is checked against."""
    analysis = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository_id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    results = (analysis.results if analysis else {}) or {}
    testing = (results.get("testing") or {}).get("metrics") or {}
    files = db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository_id).all()
    chunks = (
        db.query(CodeChunk.symbol)
        .filter(CodeChunk.repository_id == repository_id)
        .limit(400).all()
    )
    return {
        "test_cases": int(testing.get("test_cases", 0)),
        "ci_runs_tests": bool(testing.get("ci_runs_tests")),
        "languages": sorted({f.language for f in files if f.language}),
        "files": [f.path for f in files[:400]],
        "symbols": [c.symbol for c in chunks],
    }


def _session_out(db: Session, session: InterviewSession) -> InterviewOut:
    questions = (
        db.query(InterviewQuestion)
        .filter(InterviewQuestion.session_id == session.id)
        .order_by(InterviewQuestion.created_at).all()
    )
    answers = (
        db.query(InterviewAnswer)
        .filter(InterviewAnswer.session_id == session.id).all()
    )
    payload = InterviewOut.model_validate(session)
    payload.questions = [QuestionOut.model_validate(q) for q in questions]
    payload.answers = [AnswerOut.model_validate(a) for a in answers]
    return payload


@router.post("", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: InterviewCreate, user: CurrentUser, db: DbSession, request: Request
) -> InterviewOut:
    """Create a verification session with questions generated from the repository."""
    if user.role == "STUDENT" and payload.candidate_id:
        candidate = db.get(Candidate, payload.candidate_id)
        if candidate is None or candidate.user_id != user.id:
            raise ForbiddenError("You can only create a practice session for your own profile.")

    evaluation: Evaluation | None = None
    repository_id = payload.repository_id
    candidate_id = payload.candidate_id
    organization_id = None

    if payload.evaluation_id:
        evaluation = db.get(Evaluation, payload.evaluation_id)
        if evaluation is None:
            raise NotFoundError("Evaluation not found.")
        repository_id = repository_id or evaluation.repository_id
        candidate_id = candidate_id or evaluation.candidate_id
        organization_id = evaluation.organization_id

    if not repository_id:
        raise ValidationError("Provide a repository_id or an evaluation_id.")

    repository = db.get(Repository, repository_id)
    if repository is None:
        raise NotFoundError("Repository not found.")

    analysis = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == repository.id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    if analysis is None:
        raise ValidationError(
            "Questions are generated from a completed analysis. Analyse this repository first."
        )

    session = InterviewSession(
        organization_id=organization_id, evaluation_id=payload.evaluation_id,
        candidate_id=candidate_id, repository_id=repository.id, interviewer_id=user.id,
        title=payload.title, status="OPEN", started_at=datetime.now(timezone.utc),
        is_demo=repository.is_demo,
    )
    db.add(session)
    db.flush()

    generated = interview.generate_questions(
        analysis.results, repository.full_name, limit=payload.question_count * 2
    )
    if payload.categories:
        preferred = [q for q in generated if q.category in set(payload.categories)]
        generated = preferred or generated

    for question in generated[: payload.question_count]:
        data = question.to_dict()
        db.add(InterviewQuestion(
            repository_id=repository.id, evaluation_id=payload.evaluation_id,
            session_id=session.id, category=data["category"], question=data["question"],
            difficulty=data["difficulty"], rationale=data["rationale"], anchors=data["anchors"],
            expected_points=data["expected_points"], generated_by=data["generated_by"],
            generator_version=data["generator_version"],
        ))

    audit.record(db, audit.ACTION_INTERVIEW_CREATED, actor=user, target_type="interview_session",
                 target_id=session.id, organization_id=organization_id,
                 detail={"repository": repository.full_name,
                         "questions": min(payload.question_count, len(generated))},
                 request=request)
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.get("/{session_id}", response_model=InterviewOut)
def get_session(session_id: str, user: CurrentUser, db: DbSession) -> InterviewOut:
    return _session_out(db, _visible_session(db, user, session_id))


@router.get("", response_model=list[InterviewOut])
def list_sessions(
    user: CurrentUser, db: DbSession, candidate_id: str | None = None,
    repository_id: str | None = None,
) -> list[InterviewOut]:
    query = db.query(InterviewSession)
    if user.role != "ADMIN":
        organization_ids = user_organization_ids(db, user)
        own_candidate = db.query(Candidate).filter(Candidate.user_id == user.id).first()
        from sqlalchemy import or_

        conditions = [InterviewSession.interviewer_id == user.id]
        if organization_ids:
            conditions.append(InterviewSession.organization_id.in_(organization_ids))
        if own_candidate is not None:
            conditions.append(InterviewSession.candidate_id == own_candidate.id)
        query = query.filter(or_(*conditions))
    if candidate_id:
        query = query.filter(InterviewSession.candidate_id == candidate_id)
    if repository_id:
        query = query.filter(InterviewSession.repository_id == repository_id)
    rows = query.order_by(InterviewSession.created_at.desc()).limit(50).all()
    return [_session_out(db, s) for s in rows]


@router.post("/{session_id}/questions", response_model=list[QuestionOut])
def add_questions(
    session_id: str, user: CurrentUser, db: DbSession, count: int = 5, category: str | None = None
) -> list[QuestionOut]:
    """Generate additional questions for an open session."""
    session = _visible_session(db, user, session_id)
    if session.status != "OPEN":
        raise ValidationError("This session is closed.")
    if not session.repository_id:
        raise ValidationError("This session is not linked to a repository.")

    analysis = (
        db.query(RepositoryAnalysis)
        .filter(RepositoryAnalysis.repository_id == session.repository_id)
        .order_by(RepositoryAnalysis.created_at.desc())
        .first()
    )
    if analysis is None:
        raise ValidationError("No analysis is available for this repository.")

    repository = db.get(Repository, session.repository_id)
    existing = {
        q.question for q in
        db.query(InterviewQuestion).filter(InterviewQuestion.session_id == session.id).all()
    }
    generated = [
        q for q in interview.generate_questions(analysis.results, repository.full_name, limit=24)
        if q.question not in existing and (not category or q.category == category)
    ]
    created: list[InterviewQuestion] = []
    for question in generated[:count]:
        data = question.to_dict()
        row = InterviewQuestion(
            repository_id=session.repository_id, evaluation_id=session.evaluation_id,
            session_id=session.id, category=data["category"], question=data["question"],
            difficulty=data["difficulty"], rationale=data["rationale"], anchors=data["anchors"],
            expected_points=data["expected_points"], generated_by=data["generated_by"],
            generator_version=data["generator_version"],
        )
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    return [QuestionOut.model_validate(q) for q in created]


@router.post("/{session_id}/answers", response_model=AnswerOut, status_code=status.HTTP_201_CREATED)
def submit_answer(
    session_id: str, payload: AnswerIn, user: CurrentUser, db: DbSession
) -> AnswerOut:
    """Submit and assess an answer."""
    session = _visible_session(db, user, session_id)
    if session.status != "OPEN":
        raise ValidationError("This session is closed.")

    question = db.get(InterviewQuestion, payload.question_id)
    if question is None or question.session_id != session.id:
        raise NotFoundError("Question not found in this session.")

    facts = _repository_facts(db, session.repository_id) if session.repository_id else {}
    assessment = interview.assess_answer(
        {
            "question": question.question, "expected_points": question.expected_points,
            "anchors": question.anchors, "category": question.category,
        },
        payload.answer_text, facts,
    )

    answer = (
        db.query(InterviewAnswer)
        .filter(
            InterviewAnswer.session_id == session.id,
            InterviewAnswer.question_id == question.id,
        )
        .first()
    ) or InterviewAnswer(session_id=session.id, question_id=question.id)

    answer.answer_text = payload.answer_text
    answer.word_count = len(payload.answer_text.split())
    answer.assessment = assessment
    answer.score = assessment.get("score")
    answer.assessed_by = assessment.get("assessed_by", "deterministic")
    db.add(answer)
    db.commit()
    db.refresh(answer)
    return AnswerOut.model_validate(answer)


@router.post("/{session_id}/answers/{answer_id}/review", response_model=AnswerOut)
def review_answer(
    session_id: str, answer_id: str, payload: ReviewerAnswerScore,
    user: CurrentUser, db: DbSession, request: Request,
) -> AnswerOut:
    """Record the reviewer's own score, which overrides the automatic one."""
    if user.role not in ("INTERVIEWER", "ADMIN"):
        raise ForbiddenError("Only interviewers can score answers.")
    session = _visible_session(db, user, session_id)
    answer = db.get(InterviewAnswer, answer_id)
    if answer is None or answer.session_id != session.id:
        raise NotFoundError("Answer not found in this session.")
    answer.reviewer_score = payload.reviewer_score
    answer.reviewer_comment = payload.reviewer_comment
    db.add(answer)
    audit.record(db, "interview.answer_reviewed", actor=user, target_type="interview_answer",
                 target_id=answer.id, organization_id=session.organization_id,
                 detail={"reviewer_score": payload.reviewer_score,
                         "automatic_score": answer.score}, request=request)
    db.commit()
    db.refresh(answer)
    return AnswerOut.model_validate(answer)


@router.post("/{session_id}/complete", response_model=InterviewOut)
def complete_session(
    session_id: str, user: CurrentUser, db: DbSession, request: Request
) -> InterviewOut:
    """Close the session and compute the verification score.

    The reviewer's score wins wherever one was recorded. The result is an input
    to ownership confidence; it never decides a hiring outcome by itself.
    """
    if user.role not in ("INTERVIEWER", "ADMIN"):
        raise ForbiddenError("Only interviewers can complete a verification session.")
    session = _visible_session(db, user, session_id)
    answers = db.query(InterviewAnswer).filter(InterviewAnswer.session_id == session.id).all()
    if not answers:
        raise ValidationError("This session has no answers to score.")

    effective = [
        a.reviewer_score if a.reviewer_score is not None else (a.score or 0.0) for a in answers
    ]
    dimensions: dict[str, list[float]] = {}
    for answer in answers:
        for key, value in (answer.assessment.get("dimensions") or {}).items():
            dimensions.setdefault(key, []).append(float(value.get("score", 0.0)))

    session.verification_score = interview.session_score(effective)
    session.dimension_scores = {
        key: round(sum(values) / len(values), 1) for key, values in dimensions.items()
    }
    session.status = "COMPLETED"
    session.completed_at = datetime.now(timezone.utc)
    session.summary = (
        f"{len(answers)} answer(s) assessed. Verification score "
        f"{session.verification_score:.0f}/100"
        + (f", including {sum(1 for a in answers if a.reviewer_score is not None)} reviewer-scored "
           "answer(s)." if any(a.reviewer_score is not None for a in answers) else ".")
        + " This score measures how well the candidate explained their own repository. It is one "
          "input to ownership confidence and is not a hiring decision."
    )
    db.add(session)
    audit.record(db, audit.ACTION_INTERVIEW_SCORED, actor=user, target_type="interview_session",
                 target_id=session.id, organization_id=session.organization_id,
                 detail={"verification_score": session.verification_score,
                         "answers": len(answers)}, request=request)
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


@router.delete("/{session_id}", response_model=Message)
def delete_session(session_id: str, user: CurrentUser, db: DbSession) -> Message:
    session = _visible_session(db, user, session_id)
    if user.role not in ("INTERVIEWER", "ADMIN") and session.interviewer_id != user.id:
        raise ForbiddenError("Only the session owner can delete it.")
    db.delete(session)
    db.commit()
    return Message(message="Interview session deleted.")
