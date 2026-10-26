# MeshKor Lien Valuation: backend

This repository is the server side of the **MeshKor Lien Valuation portal**. The portal tells a law firm what a hospital bill is really worth.

A hospital bill shows "billed charges". These are list prices, and almost nobody pays them. Insurers pay much less, Medicare pays less again, and the hospital's own cost is lower still. In a personal-injury case or a lien dispute, the lawyer needs to show a **reasonable value** for each charge, with official sources. This system builds that report:

1. A law firm uploads the hospital bill.
2. The system reads every line and prices it against official public data:
   - the hospital's own posted rate with the patient's insurer,
   - the median of its posted rates with commercial insurers,
   - its cash price,
   - what Medicare pays this hospital,
   - the hospital's cost.
3. A MeshKor reviewer checks the result and approves it.
4. The law firm downloads a PDF report and a CSV data appendix. Every number in them points to its source file and that file's SHA-256 hash.

The web screens are in the second repository, **[Meshkor_lien-valuation_frontend](https://github.com/OneSmarterInc/Meshkor_lien-valuation_frontend)**. That repository has its own README.

---

## Contents

1. [The big picture](#1-the-big-picture)
2. [Who uses the portal](#2-who-uses-the-portal)
3. [The workflow, step by step](#3-the-workflow-step-by-step)
4. [How a bill is priced](#4-how-a-bill-is-priced)
5. [Where the numbers come from (reference data)](#5-where-the-numbers-come-from-reference-data)
6. [Repository layout](#6-repository-layout)
7. [Set up on a new PC (Windows)](#7-set-up-on-a-new-pc-windows)
8. [Settings (`.env`)](#8-settings-env)
9. [Run the portal](#9-run-the-portal)
10. [Commands you will use](#10-commands-you-will-use)
11. [Tests](#11-tests)
12. [Security and PHI rules](#12-security-and-phi-rules)
13. [Status, limits and next steps](#13-status-limits-and-next-steps)
14. [More documents](#14-more-documents)

---

## 1. The big picture

```
                    ┌──────────────────────────────┐
  Law firm  ───────▶│  Frontend (React, port 5173) │◀────── MeshKor reviewer
  (browser)         └──────────────┬───────────────┘        (browser)
                                   │  /api/...  (JSON, JWT login)
                    ┌──────────────▼───────────────┐
                    │  Backend (Django, port 8000) │   this repository
                    │  accounts · cases · refdata  │
                    └───────┬──────────────┬───────┘
                            │              │
              ┌─────────────▼───┐   ┌──────▼─────────────────────────┐
              │  PostgreSQL     │   │  pipeline/lien  (pricing step)  │
              │  users, cases,  │   │  reads the bill, matches the    │
              │  lines, flags,  │   │  hospital, prices every line    │
              │  audit log      │   └──────┬─────────────────────────┘
              └─────────────────┘          │ read-only
                                    ┌──────▼─────────────────────────┐
  Encrypted bills and EOBs ──▶      │  data/meshkor.duckdb            │
  (MESHKOR_UPLOAD_DIR, outside Git) │  CMS rate tables + hospital     │
                                    │  price files (from Parquet)     │
                                    └──────▲─────────────────────────┘
                                           │ built by pipeline/ref + duckdb_build
                                    Raw CMS downloads and hospital price files
                                    (kept unchanged, every file hashed)
```

The system has **3 parts**:

| Part | What it holds | Technology |
|---|---|---|
| **The portal backend** (`backend/`) | Logins, cases, uploads, review actions, reports, audit log | Django 5/6, Django REST Framework, SimpleJWT, PostgreSQL |
| **The pricing step** (`pipeline/lien/`) | Reads a bill, finds the hospital, and prices every line | Python, pdfplumber, DuckDB |
| **The reference data pipeline** (`pipeline/ref/`, `pipeline/hpt/`) | Turns public CMS files and hospital price files into clean tables | Python, Polars, DuckDB, Parquet |

**These rules hold everywhere:**

- **Official public sources only.** Every value comes from a CMS file or from the hospital's own price file, as downloaded.
- **Every row has lineage.** Every reference row carries `source_file`, `source_sha256`, `period`, `effective_start` and `effective_end`, so a report can always say which file and which date a number came from.
- **Raw files are never changed.** A new release goes in a new folder.
- **PHI is kept apart.** Bills and EOBs are encrypted on disk and are never in Git (see [section 12](#12-security-and-phi-rules)).

---

## 2. Who uses the portal

Each user has one **role**. The role decides what the user can see and do.

| Role | Who | What they can do |
|---|---|---|
| `firm` | A lawyer or paralegal at a law firm (our customer) | Upload a bill (with an EOB if they have one). See **only their own firm's** cases. Download a report after MeshKor releases it. Give feedback on the result. |
| `reviewer` | MeshKor staff | See every firm's cases. Check the flags, confirm the DRG, approve and send, or send back. Upload a bill on behalf of a firm (for example, when the firm emails it). |
| `admin` | MeshKor staff | Everything a reviewer can do. Later also user management. |

**The server enforces these rules, not the screen.** A firm user who asks for another firm's case gets `404 Not found`. Nothing about that case is shown.

Make users with this command (there is no sign-up page; MeshKor makes the accounts):

```powershell
python backend\manage.py create_portal_user --email reviewer@meshkor.com --password "..." --role reviewer --name "Reviewer Name"
python backend\manage.py create_portal_user --email jane@firm.com --password "..." --role firm --firm "Smith & Lee LLP" --name "Jane Doe"
```

If the firm does not exist yet, `--firm` creates it.

---

## 3. The workflow, step by step

On the screen, a case has **3 steps: 1 Upload → 2 Review → 3 Report & send.**

### Step 1: Upload (law firm, or staff for a firm)

1. The user picks the bill (PDF, Word .docx, JPG, PNG or TIFF, up to 50 MB), with an EOB if they have one. The server checks the file's first bytes, so a renamed file is refused.
2. They enter their matter reference and say who the report is for (plaintiff, defense or lien resolution).
3. They tick **"client consented"**. The server stores the time of consent.
4. The server **encrypts** the files and stores them outside the repository. The database keeps only the name, size, SHA-256 and path.
5. The server gives the case a number (`MK-2026-0001`, `MK-2026-0002`, …).
6. **The upload answers at once.** The pricing step ([section 4](#4-how-a-bill-is-priced)) runs **in the background**: a hospital PDF takes a few seconds, a scan or photo (OCR) can take a minute. The case shows **Processing**, and the Review page and the case lists fill in by themselves when it ends.
   - Who does the pricing is set by `MESHKOR_PRICING` (section 8). The default, `thread`, needs nothing extra.
   - If the server stops during pricing, the case is not lost. It is priced again the next time a reviewer opens **Cases** (or by `pricing_worker`).

### Step 2: Review (MeshKor reviewer)

The reviewer opens **Cases → (case) → Review** and sees:

- the hospital that was found, and the price file used (with its date),
- the bill total against each benchmark (billed, insurer rate, median, cash, Medicare, cost),
- every bill line with its values and its sources,
- for an inpatient stay: the MS-DRG, the length of stay and the value of the stay,
- **flags**: things a person must look at.

**Flags have 2 levels:**

| Level | Meaning | Examples |
|---|---|---|
| `check` | Must be resolved before approval | Line read with low certainty · lines do not add up to the bill total · payer rate below Medicare · confirm the MS-DRG · hospital matched by name only · price file does not cover the date of service |
| `info` | For information only | Lines packaged by Medicare · self-pay (no insurer) · no EOB uploaded · some plans pay a % of Medicare |

The reviewer resolves each `check` flag with a short note. For an inpatient stay, they confirm the DRG or type a different one. **A changed DRG is priced again at once.**

### Step 3: Report & send (MeshKor reviewer)

- The reviewer previews the report and can download the draft PDF and the CSV. A draft PDF is marked **DRAFT**.
- **Approve and send:** this works only when no `check` flag is open. The case becomes `sent`, the firm gets an email, and the downloads open for the firm.
- **Send back:** the reviewer must write why (for example, a page of the bill is missing). The case becomes `returned`.
- **Optional four-eyes rule:** with `MESHKOR_FOUR_EYES=1`, the person who resolved the flags cannot also approve the case.

### After release (law firm)

- The case shows **Ready** in **My reports**.
- The firm downloads `MK-…_valuation_report.pdf` and `MK-…_data_appendix.csv`.
- The firm tells us the outcome (reduced, partly reduced, no change) and what a fair price per report would be.

### Case statuses

```
uploaded ─▶ processing ─▶ needs_review ─▶ sent
                       ├▶ no_price_file   (hospital found, but its price file is not loaded yet)
                       └▶ error           (bill not readable, hospital not found, or data missing)
            needs_review ─▶ returned      (reviewer sent it back)
```

The reason for `no_price_file` or `error` is in the case's `status_detail`, in plain words.

**Every action is in the audit log:** sign-in, upload, case view, flag decision, DRG change, approval, return and every download. Staff see it on the **Audit log** page and in `/admin/`.

---

## 4. How a bill is priced

The code is in `pipeline/lien/`. `backend/cases/processing.py` is the **only** place where the API calls it.

### 4.1 Read the bill (`reader.py`)

- **Which file, which method:**

  | File | Read by | Exact? |
  |---|---|---|
  | PDF from the billing system (has a text layer) | `pdfplumber` text | Yes |
  | Word `.docx` | its paragraphs and tables (`python-docx`) | Yes |
  | Scanned PDF, JPG, PNG, TIFF, or a picture inside a Word file | **OCR** on this computer (`ocr.py`, RapidOCR) | No: checked by a person |

- Very large text, such as a "COPY" watermark, is ignored (by font size in a PDF, by letter height in OCR). OCR also straightens a tilted photo and applies the phone's rotation.
- **From the header:** hospital name, CCN, NPI, type of bill, MS-DRG, service dates, payer, reason for visit, stated total.
- **From each line:** `[line no] date  revenue code  [HCPCS/CPT] [modifiers]  units  description  charge`. A description that wraps onto the next line is joined back.
- Each line gets a **confidence**. It is lower when a line number is skipped or a value looks odd, and anything under 90 % becomes a `check` flag.
- **Inpatient** means a type of bill of 011x or 012x, or an MS-DRG on the bill.
- **Diagnoses:** ICD-10-CM codes on lines labelled "Diagnosis", "Dx" or "ICD-10", anywhere on the bill (a UB-04 lists them below the lines). The principal diagnosis comes first; admitting diagnoses are skipped. Each code gets its name and level from the CMS MS-DRG tables in force on the date of service (`ref_msdrg_dx`, `ref_msdrg_cc`): principal, MCC, CC or other. The DRG flag lists the MCC and CC codes, so the reviewer can see why a stay is "with MCC" or "with CC". CMS's exclusions for the principal diagnosis are not checked yet (the CMS grouper, or I/OCE for outpatient, is the planned next step).
- **OCR rules:** a line's certainty is at most the OCR certainty of its text, and never above 95 %. When OCR misses a value (often a thin "1" in the Units column, sometimes a revenue code or the description), the line is still read, the missing value gets a safe default (1 unit), its certainty drops to 85 %, and a note names what was missing. Every OCR bill gets a **check** flag, "Bill read from a scan or photo by OCR: compare the lines with the bill". The check that the lines add up to the bill total still runs.
- **The OCR engine:** RapidOCR (PP-OCR models on ONNX Runtime). It is free (Apache-2.0 licence) and runs **on this computer**: the bill is never sent anywhere. On first use it downloads its 3 model files (about 32 MB) once; after that it works offline. Speed: about 5 seconds per page. Tested on the 10 synthetic bills as clean scans and as tilted, blurred phone photos: **143 of 146 lines and 80 of 80 header fields exact**, and the 3 misses were all flagged. Tesseract, the other free engine, read 71 of 146 lines on the same images.
- A file that cannot be read at all (too blurred, an unknown layout) goes to `error`, with the reason.

### 4.2 Find the hospital (`match.py`)

The steps are tried in this order, and the first match wins:

1. **CCN** printed on the bill (the Medicare provider number).
2. **NPI**, looked up in `ref_ccn_npi` and in the NPIs listed in the price files.
3. **Name**, compared word by word with the hospital names. A name match always gets a `check` flag, so a person confirms it.

If no step matches, the case goes to `error` with the name, CCN and NPI that were read.

### 4.3 Price each line (`price.py`)

The pricing step picks **the hospital's price file in force on the date of service**.

**Outpatient: one set of values per bill line**

| Value | How it is found |
|---|---|
| **Insurer rate** (`payer_rate`) | The hospital's own posted rate for this code with the patient's insurer. When the insurer has several plans, the median of the plans is used. The insurer name on the bill is turned into a payer group (for example "Anthem", "UnitedHealthcare") by the rules in `config/payer_groups.yaml`. |
| **Median, p10, p90** | The median and the 10th and 90th percentiles of the hospital's posted rates for the same code with **commercial insurers only** (see 4.6). |
| **Cash** | The hospital's posted discounted cash price. When the hospital posts none, it is shown as "not posted", never as $0. |
| **Medicare** | OPPS rate × (0.60 × hospital wage index + 0.40). Labs use the Clinical Lab Fee Schedule. Therapy uses the Physician Fee Schedule (non-facility, Ohio). Drugs use ASP + 6 %. A status-N line is **packaged** ($0). Then Medicare's claim rules are applied **per visit** (see below). |
| **Cost** | Line charge × the hospital's **cost-to-charge ratio** from its latest Medicare cost report (HCRIS). |

**Medicare's claim rules (per visit):** `apply_claim_rules()` in `price.py`. A **visit** is one date of service, or dates at most 1 day apart; each visit is treated as its own Medicare claim. A bill that holds several visits gets an info flag listing them.

| Rule | What happens |
|---|---|
| **Comprehensive APC (status J1)** | The visit's highest-paid J1 line is the primary and is paid in full. The other J1 lines and every other OPPS line of **that visit** are packaged into it ($0). Lines on another visit are not touched. |
| **Never packaged into a J1** | Pass-through drugs and devices (status G, H), brachytherapy sources (U), vaccines (L, F), and lines Medicare pays on another fee schedule (labs with status A, therapy on the physician fee schedule, ASP drugs) keep their own rate. |
| **Multiple procedure discount** | On a visit without a J1, the highest-paid procedure with status T is paid in full; every other T unit is paid at 50 %. |
| **Revenue-code-only lines** | Paid inside the coded lines of their visit ($0). In a visit with no coded Medicare line, they have no Medicare value. |

Every change is written into the line's `medicare_source`, for example "multiple procedure discount: paid at 50 %". These rules follow the CMS OPPS policies. CMS's own outpatient code editor (I/OCE) is the planned next step; once added, it will compute these lines exactly, and these rules will stay as a cross-check.

**Contract rates that are not plain dollars:**

| What the price file says | What the pricing step does |
|---|---|
| A percentage of billed charges | % × this line's charge. Marked **estimate (\*)**. |
| "N % of Medicare" in the notes (OSU writes it this way) | N % × the Medicare rate of this line. The dollar column on that row is ignored, because it holds a factor, not a price. Marked **estimate (\*)**. |
| An estimated amount only | That amount. Marked **estimate (\*)**. |
| A "dollar" rate under $5 on a charge of $50 or more, and under half the Medicare rate | A factor the hospital put in the dollar column (OSU posts Cigna 0.62 this way). It is left out of the median and the insurer rate, and a flag counts the rows. |
| An insurer that is not in `config/payer_groups.yaml` | **No insurer rate** (never another plan's rate), and a check flag asks staff to add the name. |
| A reversal line (negative charge) | Its rates are subtracted, like its charge. |

**Inpatient: the whole stay is one MS-DRG**

| Value | How it is found |
|---|---|
| Insurer rate, median, p10, p90, cash | The DRG rows of the hospital's price file, by the same rules as above |
| Medicare | `ipps_payment()`: DRG weight × the hospital's base rate, with wage index, IME, DSH, uncompensated care, VBP and readmission factors, and capital. Outliers, transfers and new-technology payments are not included. |
| Cost | Billed total × cost-to-charge ratio |

The lines of an inpatient bill are still listed, with their charge and cost, so the reviewer can see what the stay contained.

### 4.4 When the price file does not cover the date of service

If the hospital has a price file, but it starts after the date of service, the lines are priced **twice**:

- **basis = `service_date`:** only the values that exist for that date (Medicare, cost).
- **basis = `estimate`:** the insurer rate and the median from the nearest file, all marked as estimates.

The totals, the report, the PDF and the CSV then use the **estimate** basis (`totals.basis = "estimate"`), with every insurer value marked as an estimate and the limits text saying so. The reviewer can switch between the two on the Review page, and a flag explains why.

### 4.5 Totals and coverage

- A total adds up **only the lines that have a value**.
- `totals.coverage` gives the billed dollars and the share of the bill those lines cover. When it is under 100 %, the report's "% of billed" compares the total with the billed charges of the **same lines**, and a note under the benchmark says so ("4 of 11 lines, 61 % of billed charges; the % compares those lines only"). A benchmark on less than half of the billed charges (for example a cash price posted on one lab line) is listed without a percentage, marked "not comparable with the bill". The summary sentence, the table, the PDF and the screen all use this same rule.
- A law firm user sees the values, lines and report **only after release**. Before that, the case shows progress only.

### 4.6 Which payers count in the median (decided October 26, 2026)

The median and the 10th/90th percentiles use **commercial insurers only**: employer and individual plans, ACA exchange plans, PPO networks and TPAs. **Left out:** Medicare, Medicare Advantage, Medicaid, other government plans, workers' comp and self-pay. Medicare has its own benchmark line, so counting government rates in the median too would mix two different benchmarks.

- The list of excluded groups is `NOT_COMMERCIAL` in `pipeline/lien/price.py`. Which group a plan belongs to comes from `config/payer_groups.yaml` and is worked out again on every pricing run, so a rule change there applies at once.
- ACA exchange plans (for example "CareSource - Exchange", "Buckeye Ambetter Exchange") have their own group, `ACA Exchange`, and count as commercial.
- The **patient's own insurer rate** is not affected: a Medicare Advantage patient still gets their own plan's rate in the insurer line.
- Example, OSU, MS-DRG 481: 43 posted rates; 16 government plans left out; median of the 27 commercial rates **$61,642.56** (all 43: $42,572.81).
- Many commercial contracts are a percentage of billed charges; for those the hospital's own dollar estimate is used, which follows its list prices. The report's limits text says so.

---

## 5. Where the numbers come from (reference data)

All reference data is **free public data**. The pipeline loads each file into a Parquet table, then copies every table into **one DuckDB file** (`data/meshkor.duckdb`). The pricing step reads that file read-only.

### 5.1 CMS tables (Step 1)

| Table | What it is | Used for |
|---|---|---|
| `ref_opps` | Medicare outpatient rates (OPPS Addendum B), per quarter | Medicare value of outpatient lines |
| `ref_ipps_drg`, `ref_ipps_hospital` | Inpatient DRG weights and per-hospital factors (wage index, IME, DSH, cost-to-charge) | Medicare value of a stay; wage index for OPPS |
| `ref_mpfs`, `ref_mpfs_locality` | Physician Fee Schedule | Therapy and other lines paid under MPFS |
| `ref_clfs` | Clinical Lab Fee Schedule | Lab lines |
| `ref_asp`, `ref_ndc_hcpcs` | Part B drug payment limits; NDC ⇄ HCPCS | Drug lines |
| `ref_hcris` | Hospital cost reports | Cost-to-charge ratio, cost column |
| `ref_ccn_npi`, `ref_provider` | Hospital enrollments, NPPES | Finding the hospital |
| `ref_msdrg*` | MS-DRG definitions V41–V44 (titles, diagnoses, CC/MCC) | DRG title and checks |
| `ref_hcpcs_code` | HCPCS Level II codes | Code names |
| `ref_ncci_ptp`, `ref_mue` | NCCI edits | Coding checks (planned) |
| `ref_asc`, `ref_dmepos`, `ref_ambulance`, `ref_anesthesia_*`, `ref_geo*`, `ref_quality_*`, `ref_ownership`, `ref_chow*`, `ref_nadac`, `ref_ndc_*` | Other CMS / FDA / HUD tables | Other bill types and later features |

History is loaded for **2024 to 2026** (all quarters), so a 2024 bill is priced with the 2024 rates.

The latest verify report (`data/reports/verify_latest.md`) shows **245 pass, 0 fail**.

### 5.2 Hospital price files (Step 2)

Since 2021, every US hospital must publish a **machine-readable file** (45 CFR 180) with its negotiated rates for every payer and plan. These files are the source of the insurer rate, the median and the cash price.

| Hospital | CCN | State |
|---|---|---|
| Ohio State University Hospitals | 360085 | Loaded (2,366,510 rows, file dated 2026-07-01) |
| Arthur G James Cancer Hospital | 360242 | Loaded (4,470,209 rows, file dated 2026-07-01) |
| Miami Valley Hospital | 360051 | To download (JSON layout) |
| Cleveland Clinic Hospital | 360180 | To download (large CSV) |

The loader `pipeline/ref/hospital_mrf.py` reads all 3 CMS template layouts (CSV "tall", CSV "wide", JSON) into one table, `ref_hospital_mrf`. One hospital × one download month is one release. The progress of each hospital is in `data/reports/hpt_progress.md`.

### 5.3 How data flows into the DuckDB file

```
Raw downloads (one folder per release, never edited)      MESHKOR_RAW_DIR
        │   load_ref <table>        one loader per table in pipeline/ref/
        ▼
data/ref/<table>.parquet   +  data/ref/_manifest/<table>.json   (rows, hashes, warnings)
        │   build_duckdb            copies every table, adds views and macros from sql/views.sql
        ▼
data/meshkor.duckdb
        │   verify_step1            row counts, hashes, golden values
        ▼
data/reports/verify_latest.md
```

`sql/views.sql` holds the SQL helpers the pricing step uses, for example `opps_wage_adjusted()`, `ipps_payment()`, `clfs_rate()`, `mpfs_rate()`, `asp_price()`, `mrf_rate()`, `mrf_drg()`, `msdrg_title()` and `v_hcris_latest`. Each one starts with a `-- @stmt <name>:` line.

---

## 6. Repository layout

```
backend/                      Django project
  meshkor/                    settings.py (reads .env), urls.py
  accounts/                   Firm, Profile (role), e-mail login, JWT views, create_portal_user
  cases/                      the portal itself
    models.py                 Case, CaseFile, CaseLine, Flag, Stay, Feedback, AuditEntry
    views.py, urls.py         every /api/cases/... endpoint, firms, audit
    serializers.py            JSON shapes (match docs/API_CONTRACT.md)
    storage.py                Fernet encryption of bills and EOBs
    processing.py             the one hook into the pricing step
    reports.py                report data, PDF (reportlab) and CSV
    audit.py                  writes one audit row; never breaks a request
    tests.py, tests_lien.py   API tests and pricing tests
    lien_testdb.py            small DuckDB for the pricing tests
    management/commands/      try_bill, reprocess_case
  refdata/                    LoadRun, SourceFile, VerifyRun; /api/data-sources/;
                              commands load_ref, build_duckdb, verify_step1, step1_status, check_raw
pipeline/
  lien/                       pricing step: reader, match, price, intake, db
  ref/                        one loader per reference table (incl. hospital_mrf.py)
  hpt/                        hospital price files: find, download, intake, verify, quality, progress
  common/                     config, lineage columns, raw-file access, output writer
  runner.py, duckdb_build.py, verify.py
config/
  sources.yaml                releases for the test fixtures
  sources_local.yaml          releases on the build PC (set MESHKOR_SOURCES=sources_local.yaml)
  payer_groups.yaml           insurer name → payer group (edit here, never in code)
  ccn_npi_manual.csv, ccn_npi_reclass.csv   reviewed hospital ⇄ NPI pairs
  hospital_sites.csv, hospital_taxonomies.yaml, hpt_tiers.csv   hospital price-file work list
sql/views.sql                 views and macros added to DuckDB by build_duckdb
data/                         reference data (Parquet, DuckDB) – NOT in Git, except manifests and reports
  ref/_manifest/              one JSON per table: sources, hashes, row counts
  reports/                    verify reports, download checks, progress
docs/                         detailed guides (see section 14)
tests/                        pytest tests for the pipeline; fixtures (trimmed real files + synthetic test bills)
tools/                        hpt_one.ps1 (one hospital start to finish), patch_views_sql.py
check_project.py              is all the data for the lien report here?
check_downloads.ps1           are the raw downloads complete and unchanged?
register.py                   builds data_register.xlsx (every release, file and table)
load_msdrg.py, verify_msdrg.py, register_msdrg.py   MS-DRG loader (standalone for now)
```

---

## 7. Set up on a new PC (Windows)

**You need:** Python 3.10 or later (3.13 is tested), PostgreSQL 16 or later (17 is tested), and Git. For the website you also need Node.js LTS (see the frontend README).

### Step 1: Get the code and make a virtual environment

```powershell
cd D:\Meshkor
git clone https://github.com/OneSmarterInc/Meshkor_lien-valuation_backend.git meshkor-data
cd meshkor-data
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-step2.txt
```

Always use `python -m pip …`. It installs into the active `.venv`.

**Do not copy a `.venv` folder from another path.** A venv works only in the folder where it was made. If you see `Fatal error in launcher`, delete `.venv` and make it again.

### Step 2: Make the database

```powershell
$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
& $psql -U postgres -h localhost -c "CREATE USER meshkor WITH LOGIN PASSWORD 'choose-a-password';"
& $psql -U postgres -h localhost -c "CREATE DATABASE meshkor OWNER meshkor;"
```

Check which port your PostgreSQL uses (`port =` in `C:\Program Files\PostgreSQL\17\data\postgresql.conf`). The default is 5432.

### Step 3: Make `.env`

Copy `.env.example` to `.env` in the repository root (`copy .env.example .env`) and fill in the values. It lists every setting with a short note; [section 8](#8-settings-env) explains them. The minimum is:

```
POSTGRES_DB=meshkor
POSTGRES_USER=meshkor
POSTGRES_PASSWORD=choose-a-password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DJANGO_SECRET_KEY=<50 random characters>
DJANGO_DEBUG=1
MESHKOR_FILE_KEY=<Fernet key>
```

Make the two keys like this:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Back up `MESHKOR_FILE_KEY` somewhere safe.** If you lose it, you can never open the stored bills again. **Never commit `.env`.**

### Step 4: Make the tables and the first users

```powershell
python backend\manage.py migrate
python backend\manage.py create_portal_user --email you@meshkor.com --password "..." --role admin --name "Your Name"
python backend\manage.py create_portal_user --email lawyer@firm.test --password "..." --role firm --firm "Test Law Firm" --name "Test Lawyer"
python backend\manage.py createsuperuser        # optional: for http://localhost:8000/admin/
```

### Step 5: Get the reference data

The DuckDB file is too big for Git (about 1.6 GB). Either copy `data\` from the build PC, or build it from the raw downloads:

```powershell
# in .env:  MESHKOR_RAW_DIR=<folder with the CMS downloads>   and   MESHKOR_SOURCES=sources_local.yaml
python backend\manage.py load_ref all
python backend\manage.py build_duckdb
python backend\manage.py verify_step1          # expect 0 fail in data\reports\verify_latest.md
```

---

## 8. Settings (`.env`)

`backend/meshkor/settings.py` reads `.env` from the repository root. A real environment variable wins over the same line in `.env`.

| Setting | Default | What it does |
|---|---|---|
| `DB_ENGINE` | `postgresql` | Set to `sqlite` only to run the tests quickly (see section 11). |
| `POSTGRES_DB` / `DB_NAME` | `meshkor` | Database name |
| `POSTGRES_USER` / `DB_USER` | `meshkor` | Database user |
| `POSTGRES_PASSWORD` / `DB_PASSWORD` | – | Database password |
| `POSTGRES_HOST` / `DB_HOST` | `localhost` | Database server |
| `POSTGRES_PORT` / `DB_PORT` | `5432` | Database port |
| `DJANGO_SECRET_KEY` | dev value | **Must be set (50+ characters).** Signs the login tokens. |
| `DJANGO_DEBUG` | `0` | `1` on a developer PC only |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Host names the server answers to |
| `DJANGO_SECURE` | `0` | `1` on a server behind HTTPS: secure cookies, HSTS, HTTPS redirect, and a hard stop if `DJANGO_SECRET_KEY` is missing |
| `MESHKOR_FILE_KEY` | – | **Must be set.** Fernet key that encrypts bills and EOBs. Back it up. |
| `MESHKOR_DATA_ROOT` | `<repo>/data` | Where Parquet, DuckDB and reports live |
| `MESHKOR_UPLOAD_DIR` | `<data>/uploads` | Where the encrypted bills live. Keep it outside the repository on a server. |
| `MESHKOR_RAW_DIR` | `<data>/raw` | Folder with the raw CMS downloads |
| `MESHKOR_SOURCES` | `sources.yaml` | `sources_local.yaml` on the build PC |
| `MESHKOR_PRICING` | `thread` | Who prices a new upload. `thread`: the web server, in the background (nothing else to run). `worker`: the web server only queues; run `pricing_worker` too (live server with more than one web process). `inline`: the upload waits (the tests use this). |
| `MESHKOR_PRICING_THREADS` | `2` | How many bills are priced at the same time in `thread` mode. OCR uses a lot of CPU. |
| `MESHKOR_FOUR_EYES` | `0` | `1` = a different reviewer must approve a case whose flags you resolved |
| `MESHKOR_PORTAL_URL` | `http://localhost:5173` | Link in the "report ready" email |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,…` | Website addresses allowed to call the API (production) |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_HOURS` | `30` / `12` | How long a sign-in lasts |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | console | Email for "report ready". The console backend prints the email in the server window. |

---

## 9. Run the portal

You need **2 PowerShell windows**.

**Window 1: backend**

```powershell
cd D:\Meshkor\meshkor-data
.\.venv\Scripts\Activate.ps1
python backend\manage.py runserver 8000
```

Leave it open. If it stops by itself without a message, run it with `--noreload` to see the error.

**Window 2: website** (see the frontend README)

```powershell
cd D:\Meshkor\lien-portal-frontend
npm run dev
```

Open **http://localhost:5173** and sign in.

**Try it end to end:**

1. Sign in as the firm user. Upload `tests\fixtures\test_bills\B01_TEST_bill.pdf`, tick consent and send.
2. Sign in as the reviewer. Open **Cases → MK-…**, resolve the flags, then **Approve and send**.
3. Sign in as the firm user. The case shows **Ready**. Download the PDF and the CSV.

**Check the server without the website:** http://localhost:8000/api/health/ answers `{"status": "ok"}`.

---

## 10. Commands you will use

All of these run from the repository root, with `.venv` active.

### Portal

| Command | What it does |
|---|---|
| `python backend\manage.py runserver 8000` | Starts the API on port 8000 |
| `python backend\manage.py create_portal_user --email … --password … --role firm\|reviewer\|admin [--firm "…"] [--name "…"]` | Makes or updates a user |
| `python backend\manage.py try_bill <bill.pdf> [--payer "…"] [--ccn …] [--drg …]` | Reads and prices one bill PDF and prints the lines, totals and flags. **It writes nothing.** Use it to test a new bill layout or a new price file. |
| `python backend\manage.py pricing_worker` | Prices the waiting uploads; keeps running. Only needed with `MESHKOR_PRICING=worker`. More than one is safe. |
| `python backend\manage.py pricing_worker --once` | Prices what is waiting now (also cases a server stop left in Processing), then stops |
| `python backend\manage.py reprocess_case MK-2026-0007` | Prices a case again, for example after a missing price file was loaded |
| `python backend\manage.py reprocess_case --status no_price_file` | Prices every case in that status again. Sent cases are never touched. |

### Reference data

| Command | What it does |
|---|---|
| `python backend\manage.py load_ref all` (or `load_ref ref_opps ref_clfs`) | Loads tables from the raw downloads into Parquet |
| `python backend\manage.py load_ref ref_hospital_mrf` | Loads the hospital price files listed in `sources_local.yaml` |
| `python backend\manage.py build_duckdb` | Rebuilds `data\meshkor.duckdb` from all Parquet. Close every other program that has the file open first. |
| `python backend\manage.py verify_step1` | Runs the checks and writes `data\reports\verify_latest.md` |
| `python backend\manage.py step1_status` | Latest load run per table |
| `python check_project.py` | Is all the data the lien report needs present? Writes `data\reports\check_project.md` |
| `.\check_downloads.ps1` | Are the raw downloads complete and unchanged? |
| `python register.py` | Rebuilds `data_register.xlsx` |
| `.\tools\hpt_one.ps1 -Ccn 360051 -Period 2026-11 -File "<downloaded file>" -Page "<hospital page>"` | One hospital price file, start to finish: intake → load → build → verify → quality → progress |

---

## 11. Tests

**Portal and pricing tests (36):** these tests use a temporary SQLite database, so they never touch your PostgreSQL data:

```powershell
$env:DB_ENGINE="sqlite"
python backend\manage.py test cases accounts
Remove-Item Env:DB_ENGINE          # back to PostgreSQL in this window
```

They cover login and tokens, firm isolation, upload rules, encryption, review → approve → download → feedback, the DRG change, and the pricing of the synthetic bills. The pricing checks include insurer rate, median, Medicare, cost, J1 packaging, % of Medicare, the inpatient DRG, the estimate basis and the hospital match.

**Pipeline tests (59):** these use trimmed real CMS files in `tests\fixtures\raw` and need no downloads:

```powershell
python -m pytest -q tests
```

**On real data:**

```powershell
python backend\manage.py try_bill tests\fixtures\test_bills\B01_TEST_bill.pdf
```

The 4 files in `tests\fixtures\test_bills\` are **synthetic test bills**. They have no real patient and no real visit, and each page says so.

To test on PostgreSQL instead of SQLite, the database user needs the right to make a test database (`ALTER USER meshkor CREATEDB;`). Then run the tests without `DB_ENGINE`.

---

## 12. Security and PHI rules

Bills and EOBs contain **protected health information (PHI)**. These rules are not optional:

1. **Never put a real bill, EOB or patient file in Git**, in `data\`, in a test folder or in an email. `.gitignore` blocks PDF files, `uploads/`, `bills/`, `.env` and the data files, but check `git status` before every commit anyway.
2. **Use only the synthetic test bills for testing** until the server is set up for production.
3. **Uploads are encrypted** with `MESHKOR_FILE_KEY` (Fernet: AES-128 + HMAC). The database never holds the file bytes.
4. **Keep `MESHKOR_FILE_KEY` and `DJANGO_SECRET_KEY` secret and backed up.** Never in Git, never in a chat.
5. **Everyone gets their own account.** Do not share logins, because the audit log names the person.
6. **Password guessing is slowed down** (`accounts/throttle.py`). After 5 wrong passwords in 15 minutes for one email from one computer, that computer must wait 15 minutes for that email (answer `429` with "Try again in N minutes"). One computer failing 20 times on any accounts, or one email failing 50 times from any computers, is also blocked. The owner signing in from another computer is not affected, and a correct password clears the count. Every block is written to the audit log.
7. **Firm isolation is in the API.** Do not add an endpoint that returns cases without `visible_cases(user)`.
8. **For production:** HTTPS only, `DJANGO_DEBUG=0`, a real `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`, the upload folder on encrypted storage, and backups of PostgreSQL and the upload folder. Any outside service that sees PHI (OCR, email, hosting) needs a BAA.

---

## 13. Status, limits and next steps

**Works today:**

- Login and roles
- Upload with encryption
- Automatic pricing of text PDFs
- Review with flags and DRG confirmation
- Approve or send back
- PDF and CSV report
- Email when a report is ready
- Audit log and data-sources page
- 36 portal tests and 59 pipeline tests

**Known limits:**

| Limit | What happens today | Plan |
|---|---|---|
| Scanned bills and photos | Read by local OCR (RapidOCR); every OCR bill is checked by a reviewer | Test with real scans as they arrive; tune `LOOSE_RX` in `reader.py` for new layouts |
| New bill layouts | The reader knows line lists in the order date, revenue code, code, units, description, charge | Add patterns in `reader.py` (`LINE_RX`) as real bills arrive. Test each one with `try_bill`. |
| EOBs | Stored, not read | Read the allowed and paid amounts into the report |
| Only 2 hospitals have price files | Other hospitals go to `no_price_file` | Load Miami Valley (JSON) and Cleveland Clinic, then the other Ohio hospitals |
| 2024–2025 price-file history | No free complete source | Use the estimate basis; archived files must be labeled as not official |
| Inpatient Medicare | IPPS estimate without outliers or transfers | Add outlier logic and the CMS grouper if needed |
| DRG change on the Review page | Priced again while the reviewer waits (a few seconds; an OCR bill is read again) | Keep the read lines, so only the pricing runs again |
| PDF layout | Simple one-column report | Designed report layout |

**Before going live:** a server, a domain, HTTPS, PostgreSQL backups, secrets in a vault, real email, a security review and a BAA with each vendor that sees PHI.

---

## 14. More documents

| File | What it covers |
|---|---|
| `docs/API_CONTRACT.md` | Every API endpoint and JSON shape. The frontend has the same file. |
| `docs/README-portal-api.md` | How the portal API was built, and the rules it enforces |
| `docs/README-lien.md` | The pricing step in detail |
| `docs/README-hpt.md` | Hospital price files: find, download, load, verify |
| `docs/README-mrf.md` | The first price-file load (OSU) and the table columns |
| `docs/README-msdrg.md` | MS-DRG definitions V41–V44 |
| `docs/README-step1.md` | Step 1 CMS reference data: download folders, every loader, known gaps, every source with its hash |
| `data/reports/verify_latest.md` | Latest check result for all reference tables |
| `data/reports/hpt_progress.md` | Which hospitals' price files are loaded |
