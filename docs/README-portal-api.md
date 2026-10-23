# Lien portal API (backend for the React frontend)

Date: October 23, 2026. Implements every endpoint in `docs/API_CONTRACT.md` (the same file the frontend carries). Django REST Framework + SimpleJWT + CORS. Pricing itself is not here yet: a new case stays `uploaded` until the pricing patch (`pipeline/lien`) is installed; everything else (login, upload, cases, review actions, report, downloads, audit, data sources) works today.

## What this adds

| Path | Does |
|---|---|
| `backend/accounts/` | `Firm`, `Profile` (role `firm` / `reviewer` / `admin` on Django's User), e-mail login backend, `/api/auth/login|refresh|me|logout/`, command `create_portal_user` |
| `backend/cases/` | `Case`, `CaseFile` (encrypted bill/EOB), `CaseLine`, `Flag`, `Stay`, `Feedback`, `AuditEntry`; all `/api/cases/...`, `/api/firms/`, `/api/audit/`; `reports.py` (report data, CSV, PDF); `storage.py` (Fernet encryption); `processing.py` (the one hook into the pipeline) |
| `backend/refdata/api.py` | `/api/data-sources/` from `LoadRun`, `VerifyRun` and the price-file Parquet |
| `backend/meshkor/settings.py`, `urls.py` | DRF, JWT, CORS, upload and mail settings; `/api/` routes; `/api/health/` |
| `requirements.txt` | + djangorestframework, simplejwt, cors-headers, cryptography, reportlab |
| `backend/cases/tests.py` | 6 contract tests (auth, isolation, upload rules, review → approve → download → feedback, DRG, data sources) |
| `docs/env_portal_snippet.txt` | the new `.env` lines |

## Install

```powershell
cd D:\Meshkor_Backend\meshkor-data
Expand-Archive "C:\Users\hansa\Downloads\meshkor-portal-api.zip" -DestinationPath . -Force
pip install -r requirements.txt
# add the lines from docs\env_portal_snippet.txt to .env; make MESHKOR_FILE_KEY first:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python backend\manage.py migrate
python backend\manage.py create_portal_user --email you@meshkor.com --password "..." --role admin --name "Your Name"
python backend\manage.py create_portal_user --email jane@firm.com --password "..." --role firm --firm "Smith & Lee LLP" --name "Jane Doe"
set DB_ENGINE=sqlite
python backend\manage.py test cases accounts          # 6 tests, OK
set DB_ENGINE=
python backend\manage.py runserver 8000
```

Then in the frontend folder: `copy .env.example .env`, `npm install`, `npm run dev`, open http://localhost:5173, sign in. The Vite proxy sends `/api` to port 8000, so no CORS setup is needed in development.

Quick check without the frontend:

```powershell
curl -X POST localhost:8000/api/auth/login/ -H "Content-Type: application/json" -d "{\"email\":\"jane@firm.com\",\"password\":\"...\"}"
```

## Rules the code enforces

- A firm user gets only its firm's cases; another firm's case is `404`.
- An expired or bad token is `401` (the frontend then refreshes); a role problem is `403`.
- Bills and EOBs: PDF/JPG/PNG/TIFF, 50 MB max, stored encrypted under `MESHKOR_UPLOAD_DIR`, SHA-256 of the original kept. The database never holds the file bytes. Lose `MESHKOR_FILE_KEY` and every stored bill is unreadable, so back it up.
- Every sign-in, upload, case view, flag decision, approval, return and download is one `AuditEntry` row (`/api/audit/`, also in `/admin/`).
- Approve is refused while a `check` flag is open. `MESHKOR_FOUR_EYES=1` also refuses approval by the reviewer who resolved the flags.
- Firm users can download the PDF/CSV only when the case is `sent`; staff any time (PDF says DRAFT before release).
- Money is returned as numbers; dates as `YYYY-MM-DD`; lists are paginated `{count, next, previous, results}`.

## Case status flow

`uploaded` → (pipeline) `processing` → `needs_review` | `no_price_file` | `error` → reviewer → `sent`, or `returned` for another pass. Today the pipeline hook (`cases/processing.py`) does nothing, so cases stay `uploaded`; the pricing patch fills `CaseLine`, `Flag`, `Stay`, `Case.totals/price_file/hospital_*` and moves the status.

## Changes from the contract

- `Stay.drg_source` can also be `reviewer` (a reviewer typed a different DRG in confirm).
- `GET /api/cases/{id}/report/` adds `case_number`, `matter_ref`, `hospital_name`, service dates and `setting` (the frontend ignores extra keys).
- `/api/health/` added for monitoring.

## Next patch (pricing)

`pipeline/lien/intake.py: process(case)` → read bill (PDF/images) → match hospital (NPI/name → CCN via `ref_ccn_npi`, `ref_provider`) → price each line with `mrf_rate_summary`, `opps_wage_adjusted`, `mpfs_rate`, `clfs_rate`, `v_hcris_latest`, `ipps_payment` + `mrf_drg` for inpatient → write `CaseLine`, `Flag`, `Stay`, totals → status `needs_review`. Then the designed PDF layout.
