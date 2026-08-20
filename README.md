# Atlas Document Collection

A focused take-home implementation for the Atlas AI Software Engineer assignment. It models a tax accountant’s document checklist, derives requirements from household employment data, stores uploaded files in RustFS, and routes uncertain classifications to human review.

## Quick start with Docker

The recommended demo path starts both Atlas and RustFS with one command:

```bash
docker-compose up --build
```

Open [http://localhost:8000](http://localhost:8000). The RustFS console is available at [http://localhost:9001](http://localhost:9001).

Stop the demo with:

```bash
docker-compose down
```

## Demo credentials

These are seeded local-demo accounts only; they are not production credentials.

- Accountant — username `accountant`, password `accountant-demo`
- Reviewer — username `reviewer`, password `reviewer-demo`

The accountant can upload documents, manage requirements, and view the review queue. The reviewer can approve or reject uncertain documents.

## Local Python development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The Python server expects RustFS at port 9000. For a standalone RustFS dependency, run `rustfs/rustfs:latest` on ports 9000 and 9001 before starting Uvicorn.

To reseed a fresh local database without starting the server:

```bash
.venv/bin/python -m app.seed
```

## Test

```bash
.venv/bin/pytest -q
python3 tests/browser_smoke.py
```

The latest verified suite is 19 passed. The domain and API tests run without a browser. The RustFS integration test runs automatically when the configured service is available and skips only when RustFS is unavailable. The browser smoke test covers desktop and mobile layouts, login, upload, navigation, and reviewer approval.

## Demo pages and pagination

- `/client` — Overview with collection metrics and recent activity
- `/client/documents` — Required documents and received-file inbox
- `/client/review` — Attention queue and reviewer actions
- `/client/settings` — Client/user details and accountant requirement overrides

Requirements, received documents, and review items use server-side pagination with 10 records per page. Pagination controls appear only when a section has more than 10 records. The table and inbox regions are independently scrollable.

## Product decisions

- One seeded three-person Patel household demonstrates universal documents, multiple employers, a mid-year job change, wrong-year files, unknown people, and unreadable scans.
- Requirement identity is stable across regeneration, so manual overrides are preserved.
- Matching is exact and only approved documents satisfy requirements.
- Classification is deterministic and local so the demo is reproducible; a production OCR/ML adapter can replace it later.
- Jinja server-rendered pages keep the take-home focused and locally runnable.
- The sample 1040 and W-2 fixtures are official blank IRS PDFs, renamed with client-like filenames so the classifier can exercise correct, wrong-year, and unknown-person cases. The unreadable fixture is intentionally invalid.

Official fixture sources:

- [2024 Form 1040](https://www.irs.gov/pub/irs-prior/f1040--2024.pdf)
- [Form W-2](https://www.irs.gov/pub/irs-pdf/fw2.pdf)

## Demo path

1. Start the stack with `docker-compose up --build`.
2. Sign in as `accountant` and review the Overview and Documents pages.
3. Upload a file named like `w2_2025_rohan_patel_harbor_finance.pdf`.
4. Use Settings to add an unanticipated accountant requirement.
5. Sign out and sign in as `reviewer`.
6. Open Needs review and approve or reject an uncertain document.
7. Use the pagination controls after more than 10 requirements, documents, or review items exist.
8. Observe stable-key reconciliation and exact matching as the collection status updates.
