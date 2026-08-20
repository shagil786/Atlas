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


def test_accountant_manual_requirement_accepts_household_select_value():
    with authenticated_client() as client:
        response = client.post("/requirements/manual", data={"doc_type": "1099-household", "tax_year": "2025", "person_id": ""}, follow_redirects=False)
        assert response.status_code == 303


def test_reviewer_cannot_change_requirements():
    with authenticated_client("reviewer", "reviewer-demo") as client:
        response = client.post("/requirements/reconcile", follow_redirects=False)
        assert response.status_code == 403


def test_data_pages_paginate_after_ten_items(monkeypatch):
    from app import main

    requirements = [
        {"doc_type": "w2", "tax_year": 2025, "person_name": f"Person {index}", "employer": "Employer", "status": "outstanding"}
        for index in range(11)
    ]
    documents = [
        {"id": index, "filename": f"document-{index}.pdf", "doc_type": "w2", "state": "approved"}
        for index in range(11)
    ]
    summary = {
        "client": {
            "household_name": "Test household",
            "filing_status": "single",
            "target_year": 2025,
            "prior_year": 2024,
        },
        "counts": {"total": 11, "received": 0, "outstanding": 11},
        "attention_count": 0,
    }
    monkeypatch.setattr(
        main,
        "client_page_context",
        lambda active_page, user: {
            "user": user,
            "summary": summary,
            "people": [],
            "requirements": requirements,
            "documents": documents,
            "active_page": active_page,
        },
    )
    with authenticated_client() as client:
        response = client.get("/client/documents?requirements_page=2&documents_page=2")
        assert response.status_code == 200
        assert "Person 10" in response.text
        assert "document-10.pdf" in response.text
        assert "Person 0" not in response.text
        assert "document-0.pdf" not in response.text
        assert response.text.count("Page 2 of 2") == 2


def test_accountant_review_queue_is_read_only(monkeypatch):
    from app import main

    context = {
        "user": None,
        "summary": {
            "client": {"household_name": "Test household", "filing_status": "single", "target_year": 2025, "prior_year": 2024},
            "counts": {"total": 0, "received": 0, "outstanding": 0},
            "attention_count": 1,
        },
        "people": [],
        "requirements": [],
        "documents": [{"id": 1, "filename": "uncertain.pdf", "doc_type": None, "person_name": None, "employer": None, "confidence": 0.2, "state": "needs_review", "classifier_note": "Low confidence"}],
        "active_page": "review",
    }
    monkeypatch.setattr(main, "client_page_context", lambda active_page, user: {**context, "user": user, "active_page": active_page})
    with authenticated_client() as client:
        accountant_page = client.get("/client/review")
        assert accountant_page.status_code == 200
        assert "Approve" not in accountant_page.text
        assert "Reviewer action required" in accountant_page.text
    with authenticated_client("reviewer", "reviewer-demo") as client:
        reviewer_page = client.get("/client/review")
        assert reviewer_page.status_code == 200
        assert "Approve" in reviewer_page.text
