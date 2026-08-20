import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, ConfigDict, Field

from .classifier import classify
from .config import settings
from .db import connect, hash_password, init_db, row_dict, seed_db, verify_password
from .domain import apply_matches
from .storage import ObjectStorage, content_hash

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("atlas")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
serializer = URLSafeSerializer(settings.session_secret, salt="atlas-session")
storage = ObjectStorage()


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern="^(approve|reject)$")
    doc_type: str | None = None
    tax_year: int | None = None
    person_name: str | None = None
    employer: str | None = None
    notes: str | None = None


@asynccontextmanager
async def lifespan(_app):
    init_db()
    seed_db()
    yield


app = FastAPI(title="Atlas Document Collection", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(json.dumps({"request_id": request_id, "method": request.method, "path": request.url.path, "status": response.status_code, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}))
    return response


def current_user(request: Request):
    token = request.cookies.get("atlas_session")
    if not token:
        return None
    try:
        user_id = serializer.loads(token)
    except BadSignature:
        return None
    with connect() as db:
        return row_dict(db.execute("SELECT * FROM users WHERE id=? AND active=1", (user_id,)).fetchone())


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def require_role(role: str):
    def dependency(request: Request):
        user = require_user(request)
        if user["role"] != role:
            raise HTTPException(403, "This action requires the reviewer role")
        return user
    return dependency


def client_summary(db):
    client = db.execute("SELECT * FROM clients LIMIT 1").fetchone()
    apply_matches(db, client["id"])
    counts = db.execute("SELECT status, COUNT(*) count FROM requirements WHERE client_id=? GROUP BY status", (client["id"],)).fetchall()
    count_map = {row["status"]: row["count"] for row in counts}
    attention = db.execute("SELECT COUNT(*) count FROM documents WHERE client_id=? AND state IN ('needs_review','unreadable')", (client["id"],)).fetchone()["count"]
    total = sum(count_map.values())
    received = count_map.get("received", 0) + count_map.get("not_needed", 0)
    return {"client": row_dict(client), "counts": {"total": total, "received": received, "outstanding": count_map.get("outstanding", 0)}, "attention_count": attention}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        if user and not verify_password(password, user["password_hash"]):
            user = None
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid demo credentials"}, status_code=401)
    response = RedirectResponse("/client", status_code=303)
    response.set_cookie("atlas_session", serializer.dumps(user["id"]), httponly=True, samesite="lax")
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("atlas_session")
    return response


@app.get("/client", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(require_user)):
    with connect() as db:
        summary = client_summary(db)
        people = [row_dict(r) for r in db.execute("SELECT * FROM people ORDER BY name").fetchall()]
        requirements = [row_dict(r) for r in db.execute("SELECT r.*, p.name person_name FROM requirements r LEFT JOIN people p ON p.id=r.person_id ORDER BY status='outstanding' DESC, r.doc_type, p.name").fetchall()]
        documents = [row_dict(r) for r in db.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()]
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "summary": summary, "people": people, "requirements": requirements, "documents": documents, "message": request.query_params.get("message")})


@app.post("/documents")
async def upload_document(request: Request, file: UploadFile = File(...), user=Depends(require_user)):
    content = await file.read()
    if not content or len(content) > 10_000_000:
        return RedirectResponse("/client?message=Upload must be between 1 byte and 10MB", status_code=303)
    with connect() as db:
        client = db.execute("SELECT * FROM clients LIMIT 1").fetchone()
        digest = content_hash(content)
        if db.execute("SELECT 1 FROM documents WHERE client_id=? AND file_hash=?", (client["id"], digest)).fetchone():
            return RedirectResponse("/client?message=Duplicate document detected", status_code=303)
        classification = classify(file.filename or "document", content, [r["name"] for r in db.execute("SELECT name FROM people").fetchall()], client["target_year"])
        key = f"{client['id']}/{digest}-{file.filename or 'document'}"
        try:
            storage.put(key, content, file.content_type or "application/octet-stream")
        except Exception as exc:
            logger.warning("storage upload failed: %s", exc)
            return RedirectResponse("/client?message=Document storage is unavailable", status_code=303)
        fields = {k: classification.get(k) for k in ("doc_type", "tax_year", "person_name", "employer", "confidence", "state", "note")}
        db.execute("INSERT INTO documents(client_id,object_key,file_hash,filename,doc_type,tax_year,person_name,employer,confidence,state,classifier_note,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (client["id"], key, digest, file.filename or "document", fields["doc_type"], fields["tax_year"], fields["person_name"], fields["employer"], fields["confidence"], fields["state"], fields["note"], user["id"]))
        apply_matches(db, client["id"])
    return RedirectResponse("/client?message=Document uploaded", status_code=303)


@app.post("/documents/{document_id}/review")
def review_document(document_id: int, input: ReviewInput, user=Depends(require_role("reviewer"))):
    with connect() as db:
        document = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not document:
            raise HTTPException(404, "Document not found")
        db.execute("UPDATE documents SET doc_type=?, tax_year=?, person_name=?, employer=?, state=? WHERE id=?", (input.doc_type or document["doc_type"], input.tax_year or document["tax_year"], input.person_name or document["person_name"], input.employer or document["employer"], "approved" if input.action == "approve" else "rejected", document_id))
        db.execute("INSERT INTO reviews(document_id,reviewer_id,corrections,decision,notes) VALUES (?,?,?,?,?)", (document_id, user["id"], input.model_dump_json(), input.action, input.notes))
        apply_matches(db, document["client_id"])
    return {"ok": True, "document_id": document_id, "state": "approved" if input.action == "approve" else "rejected"}


@app.post("/requirements/{requirement_id}/override")
def override_requirement(requirement_id: int, decision: str = Form(...), reason: str = Form(""), user=Depends(require_role("accountant"))):
    if decision not in {"not_needed", "removed"}:
        raise HTTPException(422, "Unsupported requirement decision")
    with connect() as db:
        req = db.execute("SELECT * FROM requirements WHERE id=?", (requirement_id,)).fetchone()
        if not req:
            raise HTTPException(404, "Requirement not found")
        db.execute("INSERT INTO requirement_overrides(requirement_id,client_id,stable_key,decision,actor_id,reason) VALUES (?,?,?,?,?,?)", (requirement_id, req["client_id"], req["stable_key"], decision, user["id"], reason))
        apply_matches(db, req["client_id"])
    return RedirectResponse("/client?message=Requirement updated", status_code=303)


@app.post("/requirements/manual")
def add_manual_requirement(doc_type: str = Form(...), tax_year: int = Form(...), person_id: int | None = Form(None), employer: str = Form(""), user=Depends(require_role("accountant"))):
    if not doc_type.strip() or tax_year < 2000 or tax_year > 2100:
        raise HTTPException(422, "Document type and a valid tax year are required")
    with connect() as db:
        client = db.execute("SELECT * FROM clients LIMIT 1").fetchone()
        stable_key = f"manual:{uuid.uuid4()}"
        db.execute("INSERT INTO requirements(client_id,stable_key,doc_type,tax_year,person_id,employer,source_rule,status,manual) VALUES (?,?,?,?,?,?,?,'outstanding',1)", (client["id"], stable_key, doc_type.strip().lower(), tax_year, person_id, employer.strip() or None, "manual"))
        apply_matches(db, client["id"])
    return RedirectResponse("/client?message=Manual requirement added", status_code=303)


@app.post("/requirements/reconcile")
def reconcile(user=Depends(require_role("accountant"))):
    with connect() as db:
        client = db.execute("SELECT id FROM clients LIMIT 1").fetchone()
        from .domain import reconcile_requirements
        reconcile_requirements(db, client["id"])
        apply_matches(db, client["id"])
    return RedirectResponse("/client?message=Requirements reconciled", status_code=303)


@app.post("/documents/{document_id}/review-form")
def review_form(document_id: int, action: str = Form(...), doc_type: str = Form(""), tax_year: str = Form(""), person_name: str = Form(""), employer: str = Form(""), notes: str = Form(""), user=Depends(require_role("reviewer"))):
    parsed_tax_year = int(tax_year) if tax_year.strip() else None
    with connect() as db:
        document = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not document:
            raise HTTPException(404, "Document not found")
        if action not in {"approve", "reject"}:
            raise HTTPException(422, "Unsupported review action")
        db.execute("UPDATE documents SET doc_type=?, tax_year=?, person_name=?, employer=?, state=? WHERE id=?", (doc_type or document["doc_type"], parsed_tax_year or document["tax_year"], person_name or document["person_name"], employer or document["employer"], "approved" if action == "approve" else "rejected", document_id))
        db.execute("INSERT INTO reviews(document_id,reviewer_id,corrections,decision,notes) VALUES (?,?,?,?,?)", (document_id, user["id"], json.dumps({"doc_type": doc_type, "tax_year": parsed_tax_year, "person_name": person_name, "employer": employer}), action, notes))
        apply_matches(db, document["client_id"])
    return RedirectResponse("/client?message=Review decision saved", status_code=303)


@app.get("/api/v1/client/summary")
def api_summary(request: Request, user=Depends(require_user)):
    with connect() as db:
        return {"data": client_summary(db), "request_id": request.state.request_id}


@app.get("/api/v1/documents")
def api_documents(user=Depends(require_user)):
    with connect() as db:
        return {"data": [row_dict(r) for r in db.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT 50").fetchall()]}


@app.post("/api/v1/documents", status_code=201)
async def api_upload_document(request: Request, file: UploadFile = File(...), user=Depends(require_user)):
    content = await file.read()
    if not content or len(content) > 10_000_000:
        raise HTTPException(422, "File must be between 1 byte and 10MB")
    with connect() as db:
        client = db.execute("SELECT * FROM clients LIMIT 1").fetchone()
        digest = content_hash(content)
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key:
            previous = db.execute("SELECT request_hash,response_json FROM idempotency_keys WHERE key=?", (idempotency_key,)).fetchone()
            if previous:
                if previous["request_hash"] != digest:
                    raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
                return JSONResponse(status_code=201, content=json.loads(previous["response_json"]))
        if db.execute("SELECT 1 FROM documents WHERE client_id=? AND file_hash=?", (client["id"], digest)).fetchone():
            raise HTTPException(409, "DUPLICATE_DOCUMENT")
        classification = classify(file.filename or "document", content, [r["name"] for r in db.execute("SELECT name FROM people").fetchall()], client["target_year"])
        key = f"{client['id']}/{digest}-{file.filename or 'document'}"
        try:
            storage.put(key, content, file.content_type or "application/octet-stream")
        except Exception as exc:
            logger.warning("storage upload failed: %s", exc)
            raise HTTPException(503, "Object storage unavailable")
        fields = {k: classification.get(k) for k in ("doc_type", "tax_year", "person_name", "employer", "confidence", "state", "note")}
        cursor = db.execute("INSERT INTO documents(client_id,object_key,file_hash,filename,doc_type,tax_year,person_name,employer,confidence,state,classifier_note,created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (client["id"], key, digest, file.filename or "document", fields["doc_type"], fields["tax_year"], fields["person_name"], fields["employer"], fields["confidence"], fields["state"], fields["note"], user["id"]))
        apply_matches(db, client["id"])
        created = row_dict(db.execute("SELECT * FROM documents WHERE id=?", (cursor.lastrowid,)).fetchone())
        response_payload = {"data": created, "request_id": request.state.request_id}
        if idempotency_key:
            db.execute("INSERT INTO idempotency_keys(key,request_hash,response_json) VALUES (?,?,?)", (idempotency_key, digest, json.dumps(response_payload)))
    return response_payload


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "details": []}, "request_id": request_id})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(part) for part in error["loc"]), "code": error["type"], "message": error["msg"]} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "The request contains invalid fields", "details": details}, "request_id": getattr(request.state, "request_id", "unknown")})
