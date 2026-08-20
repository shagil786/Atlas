from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}


def test_login_and_summary():
    with TestClient(app) as client:
        response = client.post("/login", data={"username": "accountant", "password": "accountant-demo"}, follow_redirects=False)
        assert response.status_code == 303
        summary = client.get("/api/v1/client/summary")
        assert summary.status_code == 200
        assert summary.json()["data"]["client"]["household_name"] == "Patel household"
        assert summary.json()["request_id"]


def test_api_requires_authentication():
    with TestClient(app) as client:
        assert client.get("/api/v1/client/summary").status_code == 401


def authenticated_client(username="accountant", password="accountant-demo"):
    client = TestClient(app)
    response = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert response.status_code == 303
    return client


def test_api_errors_have_structured_envelope():
    with authenticated_client() as client:
        response = client.post("/api/v1/documents")
        assert response.status_code == 422
        payload = response.json()
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert payload["error"]["details"]
        assert payload["request_id"]


def test_reviewer_role_is_required_for_review():
    with authenticated_client() as client:
        response = client.post("/documents/999/review", json={"action": "approve"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "HTTP_403"


def test_api_upload_idempotency_and_duplicate_hash(monkeypatch):
    from app import main

    monkeypatch.setattr(main.storage, "put", lambda *args, **kwargs: None)
    content = b"unique API testing fixture"
    with authenticated_client() as client:
        first = client.post("/api/v1/documents", files={"file": ("w2_2025_maya_patel_northstar_labs.pdf", content, "application/pdf")}, headers={"Idempotency-Key": "api-test-key-1"})
        second = client.post("/api/v1/documents", files={"file": ("w2_2025_maya_patel_northstar_labs.pdf", content, "application/pdf")}, headers={"Idempotency-Key": "api-test-key-1"})
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json()
        duplicate = client.post("/api/v1/documents", files={"file": ("different-name.pdf", content, "application/pdf")}, headers={"Idempotency-Key": "api-test-key-2"})
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["message"] == "DUPLICATE_DOCUMENT"


def test_extra_review_fields_are_rejected():
    with authenticated_client("reviewer", "reviewer-demo") as client:
        response = client.post("/documents/999/review", json={"action": "approve", "unexpected": True})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_accountant_can_add_manual_requirement():
    with authenticated_client() as client:
        response = client.post("/requirements/manual", data={"doc_type": "1099", "tax_year": "2025"}, follow_redirects=False)
        assert response.status_code == 303


def test_reviewer_cannot_change_requirements():
    with authenticated_client("reviewer", "reviewer-demo") as client:
        response = client.post("/requirements/reconcile", follow_redirects=False)
        assert response.status_code == 403
