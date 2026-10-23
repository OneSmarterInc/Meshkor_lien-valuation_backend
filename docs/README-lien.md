# MeshKor: the pricing step (pipeline/lien)

Date: October 23, 2026. This step turns an uploaded bill into a priced case that a reviewer checks.

## What happens when a bill is uploaded

1. **Read the bill** (`reader.py`). The PDF text is read line by line: date, revenue code, HCPCS/CPT, units, description, charge. The header gives the hospital, CCN or NPI, type of bill, MS-DRG, dates and payer. Big text (watermarks) is ignored.
2. **Find the hospital** (`match.py`). By CCN first, then NPI (`ref_ccn_npi`, price-file NPIs), then by name. A match by name gets a flag, so a person confirms it.
3. **Price it** (`price.py`), with the price file in force on the date of service.
   - **Outpatient**, one row per bill line:

     | Column | Comes from |
     |---|---|
     | Payer rate | The hospital's own posted rate with the patient's insurer (median of that insurer's plans). A percentage contract becomes % × the line charge, marked as an estimate. |
     | Median, p10, p90 | All payers' posted dollar rates for the code |
     | Cash | The hospital's posted cash price (empty when the hospital posts none) |
     | Medicare | OPPS rate, wage-adjusted for this hospital. Labs: CLFS. Therapy: physician fee schedule. Drugs: ASP. Status N lines: packaged ($0). A J1 line (comprehensive APC) packages the other lines of the visit. |
     | Cost | Charge × the hospital's cost-to-charge ratio (cost report) |
   - **Inpatient** (type of bill 011x, or an MS-DRG on the bill): the whole stay is one MS-DRG. Payer rate and median come from the DRG rows of the price file; Medicare from `ipps_payment()`; cost from billed × CCR.
4. **Flags** for the reviewer: low read certainty, totals that do not add up, no rate for the payer, packaged lines, no EOB, a DRG to confirm, a hospital matched by name, a date of service outside the price file.
5. **Status**: `needs_review` (priced), `no_price_file` (hospital found, no price file loaded), or `error` (bill not readable, hospital not found, DuckDB missing). The reason is in `status_detail`.

When the price file does not cover the date of service, the lines are also priced with the nearest file under **basis = estimate**, and a flag says so.

## Totals and coverage

A total adds up only the lines that have a value. `totals.coverage` gives the share of billed charges those lines cover. When it is under 100 %, the report says so next to the benchmark and the "% of billed" compares with the billed amount of the same lines.

## Commands

```powershell
cd D:\Meshkor\meshkor-data
.venv\Scripts\activate
python -m pip install -r requirements.txt        # adds pdfplumber

# 1. Tests (17, with the synthetic bills and a tiny test DuckDB)
$env:DB_ENGINE="sqlite"
python backend\manage.py test cases accounts

# 2. Try a test bill against your real data (writes nothing)
python backend\manage.py try_bill tests\fixtures\test_bills\B01_TEST_bill.pdf
python backend\manage.py try_bill tests\fixtures\test_bills\B08_TEST_bill.pdf

# 3. Price a case again (for example after loading a price file)
python backend\manage.py reprocess_case MK-2026-0007
python backend\manage.py reprocess_case --status no_price_file
```

`try_bill` needs `data\meshkor.duckdb` with the price file loaded (`ref_hospital_mrf`) and the Step 1 tables. Run `python backend\manage.py build_duckdb` first if you loaded anything new.

## Limits (today)

- **Scans and photos are not read.** A bill without a text layer goes to `error`. Reading scans needs OCR; most OCR services take the PHI off the server, so this is a separate decision.
- The reader knows line lists in the order date, revenue code, code, units, description, charge. A new layout may need a new pattern in `reader.py` (`LINE_RX`).
- Medicare inpatient is the IPPS estimate (no outliers, transfers or new-technology add-ons).
- EOBs are stored but not read yet.
- Pricing runs inside the upload request (a few seconds per bill). A background queue comes later, if needed.

## Files

| File | Does |
|---|---|
| `pipeline/lien/reader.py` | PDF → header fields and lines |
| `pipeline/lien/match.py` | CCN / NPI / name → hospital |
| `pipeline/lien/price.py` | Lines → payer, median, cash, Medicare, cost; DRG stay; flags |
| `pipeline/lien/intake.py` | Runs the 3 steps for a case and saves lines, flags, stay, totals |
| `pipeline/lien/db.py` | Read-only DuckDB connection (closed after each case) |
| `backend/cases/processing.py` | `start()` on upload, `reprice()` after a DRG change |
| `backend/cases/lien_testdb.py`, `tests_lien.py` | Test DuckDB and 11 pricing tests |
| `backend/cases/management/commands/try_bill.py`, `reprocess_case.py` | Commands above |
| `tests/fixtures/test_bills/*.pdf` | 4 synthetic test bills (no real patient) |
