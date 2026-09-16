"""Version 1 of the RepoLens API."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    candidates,
    evaluations,
    interviews,
    jobs,
    policies,
    reports,
    repositories,
    students,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(repositories.router)
api_router.include_router(jobs.router)
api_router.include_router(evaluations.router)
api_router.include_router(candidates.router)
api_router.include_router(interviews.router)
api_router.include_router(policies.router)
api_router.include_router(students.router)
api_router.include_router(reports.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
