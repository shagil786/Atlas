# Atlas Document Collection Take-Home

## Title and metadata

- Status: Approved design, implementation planning next
- Date: 2026-08-20
- Audience: Atlas AI hiring reviewers and the implementation agent
- Source: Atlas Software Engineer take-home assignment email and approved brainstorming decisions

## Context

Atlas asks for a usable screen showing a tax client’s document-collection status, including derived requirements, received documents, outstanding items, uncertain classifications, and awkward files. The submission must include a public repository, tests, README, and a 3–5 minute narrated demo.

The repository is empty, so the implementation can establish a focused architecture without migration or compatibility constraints. The design favors a complete, reviewable vertical slice over breadth: one seeded household, generic rules for the supported document types, deterministic local classification, and explicit human review.

## Functional requirements

- **FR-1:** The system MUST authenticate seeded accountant and reviewer users with signed sessions.
- **FR-2:** The system MUST display one client’s collection progress, received documents, outstanding requirements, and attention items.
- **FR-3:** The system MUST derive universal 1040/ID requirements and one W-2 requirement per person/employer.
- **FR-4:** The system MUST reconcile regenerated requirements by stable identity while preserving manual overrides and additions.
- **FR-5:** The system MUST accept real document uploads into RustFS and persist metadata in SQLite.
- **FR-6:** The system MUST classify files deterministically with type, year, person, employer, and confidence fields.
- **FR-7:** The system MUST route uncertain, unreadable, wrong-year, and unknown-person files to visible attention states.
- **FR-8:** Reviewers MUST be able to edit metadata, approve corrected classifications, or reject files.
- **FR-9:** The system MUST satisfy requirements only through exact approved metadata matches.
- **FR-10:** The system MUST provide a versioned summary API with validated inputs and structured errors.
- **FR-11:** The system MUST prevent duplicate upload side effects through idempotency and duplicate-file handling.

## Non-functional requirements

- **NFR-1:** The app MUST start from Docker Compose with FastAPI, SQLite, and RustFS and require no external service credentials.
- **NFR-2:** The UI MUST work at 320px, 768px, and desktop widths without horizontal scrolling.
- **NFR-3:** Interactive controls MUST be keyboard accessible with visible focus, labels, and associated validation errors.
- **NFR-4:** Tests MUST cover domain rules, RustFS integration, routes/authorization, failure behavior, and one end-to-end workflow.
- **NFR-5:** Every request MUST have a request ID and structured log fields for route, status, latency, and authenticated user when present.
- **NFR-6:** Error responses MUST omit stack traces, credentials, and object-store internals.

## Acceptance criteria

- **AC-1 (FR-1, FR-2):** Given seeded credentials, when a user signs in, then the correct role-specific workspace is displayed with collection counts and attention items.
- **AC-2 (FR-3, FR-4):** Given a household with a mid-year job change, when requirements are regenerated, then the new W-2 requirement appears and prior manual overrides remain unchanged.
- **AC-3 (FR-5, FR-6):** Given a supported sample file, when an accountant uploads it, then the file exists in RustFS, metadata exists in SQLite, and deterministic classification is visible.
- **AC-4 (FR-7, FR-8):** Given a low-confidence file, when a reviewer edits and approves its metadata, then the review state changes and the dashboard recalculates.
- **AC-5 (FR-9):** Given a wrong-year or unknown-person file, when it is approved, then it remains unmatched and the related requirement remains outstanding.
- **AC-6 (FR-10, FR-11):** Given a malformed request or repeated upload, when the API receives it, then it returns the specified structured status/error response without duplicate side effects.
- **AC-7 (NFR-1 through NFR-6):** Given a fresh checkout, when a reviewer follows the README and runs the test suite, then the stack starts locally, tests complete, and the core workflow is usable with accessible responsive states.

## Edge cases

- **EC-1:** RustFS rejects or times out during upload; SQLite MUST not retain a committed document record for an object that was not stored.
- **EC-2:** A referenced RustFS object is missing; the document MUST remain visible with a recoverable storage error.
- **EC-3:** A file is unreadable; it MUST be represented as `unreadable` and never satisfy a requirement.
- **EC-4:** A file belongs to the wrong year or unknown person; it MUST remain unmatched and visible for attention.
- **EC-5:** A reviewer submits invalid corrected metadata; the response MUST identify field-level validation errors and preserve safe form values.
- **EC-6:** A non-authorized role attempts a state-changing action; the request MUST return/redirect as forbidden without mutation.

## API contracts

```text
GET /api/v1/client/summary
200 { data: { client: ClientSummary, counts: CollectionCounts, attention_count: number }, request_id: string }

POST /api/v1/documents
201 { data: Document, request_id: string }
409 { error: { code: "DUPLICATE_DOCUMENT" | "IDEMPOTENCY_CONFLICT", message: string, details: [] }, request_id: string }

All JSON errors:
{ error: { code: string, message: string, details: [{ field?: string, code: string, message: string }] }, request_id: string }
```

HTML form routes use the same domain services and authorization rules. Boundary schemas are Pydantic models. JSON status codes are `200`, `201`, `401`, `403`, `404`, `409`, `422`, and `500` as applicable.

## Data models

| Entity | Required fields and constraints |
|---|---|
| User | id, username unique, password_hash, role enum, active |
| Client | id, household_name, filing_status, target_year, prior_year |
| Person | id, client_id, name, relationship, required_for_universal_docs |
| Employment | id, person_id, employer, year, effective dates |
| Requirement | id, client_id, stable_key unique per client, type, year, person/employer references, status |
| RequirementOverride | id, requirement_id or manual key, decision enum, actor_id, reason |
| Document | id, client_id, object_key unique, hash, filename, detected metadata, confidence, lifecycle state |
| Review | id, document_id, reviewer_id, corrections, decision, notes |

## Out of scope

- Production deployment, cloud credentials, external OCR/AI providers, notifications, billing, and integrations.
- Client self-service, user registration, password reset, multi-tenant administration, and granular policy configuration.
- A full event-sourced audit system, generalized workflow engine, generalized rule plugin marketplace, or SPA frontend.

## Summary

Build a complete, locally runnable take-home submission for the Atlas AI Software Engineer assignment: a tax accountant’s document-collection workspace showing received, outstanding, and attention-required documents for one seeded client household.

The implementation will optimize for a credible finished vertical slice within the assignment’s suggested 5–6 hours. It will demonstrate generic domain rules, safe re-derivation, human review of uncertain classifications, role-aware access, real object storage, tests, README documentation, and a short demo path.

## Architecture

- FastAPI modular monolith with Jinja server-rendered pages and a small JSON surface where useful.
- Pydantic schemas validate every JSON and form boundary before service-layer execution.
- SQLite stores application metadata and domain state.
- RustFS provides S3-compatible object storage and runs locally through Docker Compose.
- A storage interface isolates the application from the RustFS client and supports deterministic tests.
- Seeded demo users authenticate through signed session cookies; no external identity provider is required.
- Roles are `accountant` and `reviewer`.
- One custom three-person household is seeded with multiple employers and a mid-year job change.
- A narrow rule registry supports the initial document rules and makes future document-type rules addable without creating a generalized plugin framework.
- JSON endpoints use `/api/v1`; HTML routes remain unversioned because they are server-rendered browser views.

## Domain model and behavior

Core records:

- `users`: username, password hash, role, active flag.
- `clients`: household name, filing status, target tax year, and prior tax year.
- `people`: client, name, relationship, and whether the person is required for universal documents.
- `employments`: person, employer, year, and effective dates.
- `requirements`: generated expected document, stable key, source rule, status, and timestamps.
- `requirement_overrides`: requirement decision (`removed`, `not_needed`, or manual addition), actor, reason, and timestamps.
- `documents`: RustFS object key, original filename, file metadata, detected type/year/person/employer, confidence, lifecycle state, and timestamps.
- `reviews`: document, reviewer, corrections, decision, notes, and timestamps.

Requirement generation:

1. Generate one prior-year completed return and one government ID for every required household person.
2. Generate one target-year W-2 per employer/person from employment data.
3. Give each generated requirement a stable identity based on document type, tax year, person, and employer where applicable.
4. Reconcile regenerated requirements by stable identity instead of replacing the current list.
5. Preserve manual removals, `not_needed` decisions, and manually added requirements.
6. Mark newly derived requirements outstanding until an approved exact-match document satisfies them.

Document processing:

`upload → RustFS object write → SQLite metadata record → deterministic filename/rule classifier → confidence decision → review or approval → exact requirement matching → dashboard recalculation`

The classifier is local and deterministic. It extracts document type, tax year, person, employer, and confidence from filename conventions and seeded rules. It must produce cases for confident files, low-confidence files, wrong-year files, unknown-person files, and unreadable scans.

Matching is strict: type, tax year, person, and employer must match the requirement. A wrong-year, unknown-person, unreadable, rejected, or unapproved document never silently satisfies a requirement.

Document lifecycle states are `needs_review`, `approved`, `rejected`, and `unreadable`. Reviewers can edit metadata, approve a corrected classification, or reject a file. Failed RustFS writes must not leave partial document records; missing objects are surfaced as errors rather than silently removed.

## UI, API, and access control

The primary experience is an operations split view:

- Sidebar: client, overview, documents, needs review, settings.
- Overview: collection percentage, received/outstanding counts, and attention count.
- Documents: filterable table with type, person, employer, tax year, confidence, and state.
- Needs review: focused cards with file access, detected metadata, confidence explanation, correction fields, and approve/reject actions.
- Upload: multipart file upload with optional accountant metadata; classifier output is visible before review resolution.

Frontend quality requirements:

- The split view MUST work at 320px, 768px, and desktop widths without horizontal scrolling; the sidebar collapses to a keyboard-accessible menu below the desktop breakpoint.
- UI MUST use a small tokenized palette, consistent spacing, clear typography, and color plus text/icons for status communication.
- Data-dependent views MUST provide loading, empty, error, and success states. Failed uploads and review actions MUST preserve user-entered correction data where safe.
- All interactive controls MUST be keyboard reachable, have visible focus, and expose accessible names and error associations. Reduced-motion preferences MUST be honored.

Route surface:

- `GET /login`, `POST /login`, `POST /logout`
- `GET /client`, `GET /client/documents`, `GET /client/review`
- `POST /documents`
- `POST /api/v1/documents` for the validated JSON upload contract
- `POST /documents/{id}/review`
- `POST /requirements/{id}/override`
- `POST /requirements/manual` for accountant-created requirements the rules did not anticipate
- `POST /requirements/reconcile`
- `GET /api/v1/client/summary` returns the authenticated client’s collection counts and attention count; all other UI reads use server-rendered pages.

API contract rules:

- `GET /api/v1/client/summary` returns `200` with `{ "data": { "client": ..., "counts": ..., "attention_count": ... }, "request_id": ... }`.
- Boundary validation returns `422`; unauthenticated requests return `401`; authenticated but unauthorized requests return `403`; missing resources return `404`; duplicate uploads return `409`; unexpected failures return `500`.
- JSON failures use `{ "error": { "code": "...", "message": "...", "details": [...] }, "request_id": "..." }` without stack traces or object-store internals.
- Browser upload forms include a generated `Idempotency-Key`; repeated keys return the original result for the same request, while an identical file hash for the same client returns `409 DUPLICATE_DOCUMENT`.
- The application emits a request ID for every request and structured logs containing request ID, user ID when authenticated, route, status, and latency. Rate limiting is out of scope for the local-only submission.

Authorization is enforced in route dependencies, not only by hiding UI controls. Accountants can view the workspace, upload files, manage requirement overrides, and view review items. Reviewers can view the workspace and perform metadata corrections and approve/reject decisions. All state-changing operations use POST and return to the relevant page with success/error feedback.

Authentication uses seeded local demo accounts with hashed passwords and signed session cookies. There is no account registration, password reset, external OAuth/OIDC, multi-tenant support, or client-facing portal.

## Runtime and submission

- Docker Compose starts FastAPI, SQLite-backed application storage, and RustFS.
- A seed command creates the household, users, employment history, initial requirements, sample documents, and attention cases.
- RustFS integration tests run against the real Compose service.
- Domain tests use isolated fakes/in-memory storage where object-store behavior is not the subject under test.
- README documents startup, demo credentials, test commands, architecture decisions, omitted features, and next steps.
- The public repository includes realistic sample 1040/W-2-style files without secrets or private personal data.
- The 3–5 minute video demonstrates login, the split-view status dashboard, a late-disclosure reconciliation, a low-confidence correction, wrong-year/unknown-person handling, and the final status update.

Delivery priority:

- Must ship: domain rules, stable-key reconciliation, exact matching, upload/review workflow, seeded roles, split-view dashboard, RustFS demo storage, focused tests, README, and video path.
- Polish after the must-ship path is green: visual refinement, richer filters, additional sample files, and expanded API contract tests.
- No polish item may delay or weaken the must-ship acceptance criteria.

## Test plan and acceptance criteria

Domain tests must cover:

- Universal 1040 and government-ID requirements.
- One W-2 per employer/person.
- A mid-year job change creating a second W-2 requirement.
- Stable-key re-derivation preserving removed, not-needed, and manually added decisions.
- Exact matching and non-matching wrong-year/unknown-person cases.
- Classifier outcomes for confident, low-confidence, unreadable, wrong-year, and unknown-person files.

Integration/API tests must cover:

- Real RustFS upload and retrieval.
- Atomic behavior when object storage fails.
- Login, logout, signed-session handling, and role restrictions.
- Upload, review correction, approval/rejection, override, reconciliation, and dashboard counts.

One end-to-end smoke path must sign in as an accountant, upload a file, switch to a reviewer, correct and approve it, and verify the dashboard changes. The application is acceptable when a fresh reviewer can start it from the README, run the tests, log in with seeded credentials, understand the status within one screen, and complete the review workflow without hidden manual database edits.

The API contract test must also verify the versioned summary response, validation/error envelope, authorization status codes, request ID propagation, and duplicate-upload behavior.

## Explicit assumptions and defaults

- The repository is a new empty project; no existing framework, database, UI, or Git history is preserved.
- The target tax year and client scenario are seeded and fixed for the demo, while requirement logic remains generic for the supported document rules.
- RustFS is required for the normal demo path and is configured through Docker Compose; tests that do not exercise object storage do not require a running RustFS service.
- No production deployment, cloud credentials, OCR provider, external AI service, billing, notifications, or full audit-event system is included.
- The assignment’s suggested Monday 24 August 2026 timeline is treated as a target, not a hard product deadline.
