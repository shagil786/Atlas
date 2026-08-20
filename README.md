# Atlas Document Collection

A focused take-home implementation for the Atlas AI Software Engineer assignment. It models a tax accountant’s document checklist, derives requirements from household employment data, stores uploaded files in RustFS, and routes uncertain classifications to human review.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker run --rm -d --name atlas-rustfs -p 9000:9000 -p 9001:9001 rustfs/rustfs:latest /data
uvicorn app.main:app --reload
```

Open http://localhost:8000. Demo credentials:

- Accountant: `accountant` / `accountant-demo`
- Reviewer: `reviewer` / `reviewer-demo`

For the full app stack, use `docker-compose up --build` (or `docker compose up --build` when the Compose plugin is available). The application expects RustFS at port 9000 and creates the `atlas-documents` bucket on first upload.

To reseed a fresh local database without starting the server:

```bash
.venv/bin/python -m app.seed
```

## Test

```bash
pytest -q
```

The domain tests run without RustFS. The RustFS integration test runs automatically when the configured service is available and skips only when RustFS is unavailable.

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

1. Sign in as `accountant` and review the collection status.
2. Upload a file named like `w2_2025_rohan_patel_harbor_finance.pdf`.
3. Sign in as `reviewer` and correct/approve any low-confidence file through the review API.
4. Show that wrong-year, unknown-person, and unreadable files remain in the attention queue.
5. Explain the stable-key reconciliation behavior and test coverage.
