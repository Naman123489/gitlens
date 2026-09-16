"""API tests: authentication, authorization boundaries and validation."""

from __future__ import annotations

import pytest

from tests.conftest import auth


class TestAuthentication:
    def test_register_and_sign_in(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com", "password": "TestPassw0rd!x",
                "full_name": "New User", "role": "STUDENT",
            },
        )
        assert response.status_code == 201
        assert response.json()["user"]["role"] == "STUDENT"

        signin = client.post(
            "/api/v1/auth/login",
            json={"email": "new@example.com", "password": "TestPassw0rd!x"},
        )
        assert signin.status_code == 200
        assert signin.json()["tokens"]["access_token"]

    def test_password_is_never_returned(self, client, student_token):
        response = client.get("/api/v1/auth/me", headers=auth(student_token))
        body = response.text.lower()
        assert "password" not in body
        assert "testpassw0rd" not in body

    def test_duplicate_email_is_rejected(self, client, student_token):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "student@example.com", "password": "TestPassw0rd!x",
                "full_name": "Impostor", "role": "STUDENT",
            },
        )
        assert response.status_code == 409

    def test_weak_password_is_rejected(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@example.com", "password": "password123",
                "full_name": "Weak", "role": "STUDENT",
            },
        )
        assert response.status_code == 422

    def test_admin_role_cannot_be_self_assigned(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "sneaky@example.com", "password": "TestPassw0rd!x",
                "full_name": "Sneaky", "role": "ADMIN",
            },
        )
        assert response.status_code == 422

    def test_wrong_password_does_not_reveal_whether_the_account_exists(self, client, student_token):
        known = client.post(
            "/api/v1/auth/login",
            json={"email": "student@example.com", "password": "WrongPassw0rd!"},
        )
        unknown = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "WrongPassw0rd!"},
        )
        assert known.status_code == unknown.status_code == 401
        assert known.json()["error"]["message"] == unknown.json()["error"]["message"]

    def test_unauthenticated_requests_are_rejected(self, client):
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get("/api/v1/repositories").status_code == 401

    def test_invalid_token_is_rejected(self, client):
        response = client.get("/api/v1/auth/me", headers=auth("not-a-real-token"))
        assert response.status_code == 401

    def test_refresh_token_issues_a_new_access_token(self, client):
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "refresh@example.com", "password": "TestPassw0rd!x",
                "full_name": "Refresh", "role": "STUDENT",
            },
        ).json()
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": registered["tokens"]["refresh_token"]},
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_access_token_cannot_be_used_as_a_refresh_token(self, client, student_token):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": student_token})
        assert response.status_code == 401


class TestAuthorization:
    def test_student_cannot_create_a_job(self, client, student_token):
        response = client.post(
            "/api/v1/jobs",
            headers=auth(student_token),
            json={"title": "Engineer", "description": "Requirements:\n- Python\n"},
        )
        assert response.status_code == 403

    def test_student_cannot_create_a_candidate(self, client, student_token):
        response = client.post(
            "/api/v1/candidates", headers=auth(student_token), json={"full_name": "Someone"},
        )
        assert response.status_code == 403

    def test_student_cannot_reach_admin_endpoints(self, client, student_token):
        assert client.get("/api/v1/admin/health", headers=auth(student_token)).status_code == 403
        assert client.get("/api/v1/admin/audit-logs", headers=auth(student_token)).status_code == 403

    def test_interviewer_cannot_reach_admin_endpoints(self, client, interviewer_token):
        assert client.get("/api/v1/admin/users", headers=auth(interviewer_token)).status_code == 403

    def test_interviewer_can_create_a_job(self, client, interviewer_token):
        response = client.post(
            "/api/v1/jobs",
            headers=auth(interviewer_token),
            json={
                "title": "Backend Engineer",
                "description": "Requirements:\n- Strong Python\n- SQL\n\nNice to have:\n- Docker\n",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert {r["skill"] for r in body["requirements"]} >= {"python", "sql"}

    def test_one_organization_cannot_read_another_s_candidates(self, client, interviewer_token):
        created = client.post(
            "/api/v1/candidates", headers=auth(interviewer_token), json={"full_name": "Private"},
        ).json()

        other = client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com", "password": "TestPassw0rd!x",
                "full_name": "Other Interviewer", "role": "INTERVIEWER",
                "organization_name": "Other Org",
            },
        ).json()["tokens"]["access_token"]

        response = client.get(f"/api/v1/candidates/{created['id']}", headers=auth(other))
        # 404 rather than 403: the API must not confirm that the record exists.
        assert response.status_code == 404
        assert client.get("/api/v1/candidates", headers=auth(other)).json()["items"] == []

    def test_disclosure_can_only_be_written_by_the_candidate(self, client, interviewer_token, student_token):
        candidate_id = client.get("/api/v1/auth/me", headers=auth(student_token)).json()["candidate_id"]
        response = client.put(
            f"/api/v1/candidates/{candidate_id}/disclosure",
            headers=auth(interviewer_token),
            json={"used_ai": True, "purposes": ["testing"]},
        )
        assert response.status_code in (403, 404)


class TestValidation:
    def test_unknown_repository_returns_not_found(self, client, student_token):
        response = client.get("/api/v1/repositories/deadbeef", headers=auth(student_token))
        assert response.status_code == 404

    def test_import_requires_owner_and_name(self, client, student_token):
        response = client.post(
            "/api/v1/repositories/import", headers=auth(student_token), json={"full_name": "flask"},
        )
        assert response.status_code == 422

    def test_evaluation_requires_an_analysis_first(self, client, student_token, db):
        from app.models import Repository, User

        user = db.query(User).filter(User.email == "student@example.com").one()
        repository = Repository(
            owner_user_id=user.id, name="demo", full_name="demo/demo",
            clone_url="https://github.com/demo/demo.git",
        )
        db.add(repository)
        db.flush()

        response = client.post(
            "/api/v1/evaluations",
            headers=auth(student_token),
            json={"repository_id": repository.id},
        )
        assert response.status_code == 422
        assert "analysed" in response.json()["error"]["message"]

    def test_job_parse_preview_does_not_persist(self, client, interviewer_token):
        response = client.post(
            "/api/v1/jobs/parse",
            headers=auth(interviewer_token),
            json={"title": "ML Engineer", "description": "Requirements:\n- PyTorch\n- Python\n"},
        )
        assert response.status_code == 200
        assert {r["skill"] for r in response.json()["requirements"]} >= {"pytorch", "python"}
        assert client.get("/api/v1/jobs", headers=auth(interviewer_token)).json()["total"] == 0

    def test_errors_use_a_consistent_shape(self, client, student_token):
        body = client.get("/api/v1/repositories/missing", headers=auth(student_token)).json()
        assert set(body["error"]) >= {"code", "message", "detail", "request_id"}


class TestSystemEndpoints:
    def test_health_is_public(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_openapi_is_served(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert len(response.json()["paths"]) > 40

    def test_security_headers_and_request_id_are_present(self, client):
        response = client.get("/health")
        assert response.headers["x-request-id"]
        assert response.headers["x-response-time-ms"]


class TestPolicyEndpoints:
    def test_creating_a_policy_twice_produces_two_versions(self, client, interviewer_token):
        weights = {
            "technical_quality": 0.3, "architecture": 0.1, "job_relevance": 0.2,
            "ownership": 0.2, "testing": 0.1, "documentation": 0.03,
            "git_engineering": 0.03, "security": 0.02, "ai_utilization": 0.02,
        }
        first = client.post(
            "/api/v1/policies", headers=auth(interviewer_token),
            json={"name": "Team policy", "weights": weights},
        ).json()
        second = client.post(
            "/api/v1/policies", headers=auth(interviewer_token),
            json={"name": "Team policy", "weights": {**weights, "testing": 0.2}},
        ).json()

        assert first["version"] == 1
        assert second["version"] == 2
        versions = client.get(
            f"/api/v1/policies/{second['id']}/versions", headers=auth(interviewer_token),
        ).json()
        # The earlier version is retained so its evaluations stay explainable.
        assert {entry["version"] for entry in versions} == {1, 2}

    def test_presets_are_available(self, client, interviewer_token):
        response = client.get("/api/v1/policies/presets", headers=auth(interviewer_token))
        assert response.status_code == 200
        assert len(response.json()) >= 3
