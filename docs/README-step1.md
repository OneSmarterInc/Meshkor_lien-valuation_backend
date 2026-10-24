# meshkor-data — Step 1: CMS reference data

> This was the repository README until October 24, 2026. It is kept here unchanged as the detailed guide to the Step 1 reference data. The project overview is now in the main `README.md`. Some lines describe the state on October 17–19, 2026 (for example, "no web API"); the portal API was added later.

This repository builds the Step 1 national reference tables (Spec v4, Oct 16, 2026) from free public CMS downloads. No PHI.

**Decisions (Oct 17, 2026)**

| Decision | Choice |
|---|---|
| Django's own records (load runs, source files, verify runs) | PostgreSQL |
| Reference data | ZSTD Parquet (main copy) and **tables** in `data/meshkor.duckdb` |
| Web API in Step 1 | None. You get management commands and the Django admin only. |

## 1. How it fits together

```
<raw folder>/<release folder>/                   downloads here, unchanged (section 3)
        │  pipeline/ref/<loader>.py               one loader per table (plain Python + Polars)
        ▼
data/ref/<table>.parquet  (+ _manifest/<table>.json)
        │  pipeline/duckdb_build.py              copies all Parquet into DuckDB tables
        ▼
data/meshkor.duckdb       tables + views/macros from sql/views.sql
        │  pipeline/verify.py                    Spec §8 checks
        ▼
data/reports/verify_latest.md                    send this file for review
```

Django (`backend/`) runs the same steps and records each run in PostgreSQL. The pipeline does not import Django, so Steps 2–5 can use it as is.

## 2. Setup (Windows, macOS or Linux)

1. Install Python 3.10 or later and PostgreSQL 16 or later. (No server yet? Set `DB_ENGINE=sqlite` in `.env` and skip step 2.)
2. Create the database:
   ```sql
   CREATE USER meshkor WITH PASSWORD 'change-me';
   CREATE DATABASE meshkor OWNER meshkor;
   ```
3. Install the packages and settings:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   copy .env.example .env            # then edit the PostgreSQL password
   python backend/manage.py migrate
   python backend/manage.py createsuperuser   # for the admin site
   ```
4. Check the code on the test files (no downloads necessary):
   ```bash
   python -m pytest -q               # 45 tests
   ```

**Disk and memory:** NPPES needs about 12 GB in `data/work/` while it loads (the CSV is taken out of the zip), plus about 1 GB of output. `ref_mpfs` has 12 quarters of about 2 million rows each; the loader writes one quarter at a time, so memory holds one quarter only. Load `ref_mpfs` alone on a PC with 8 GB of RAM. `data/meshkor.duckdb` is about 1–2 GB.

## 3. Where the downloads are

On the build PC the raw downloads are in **`D:\Datasetof CMS`**, one folder per release, extracted next to the original zip. Two lines in `.env` point the pipeline there:

```
MESHKOR_RAW_DIR=D:/Datasetof CMS
MESHKOR_SOURCES=sources_local.yaml
```

`config/sources_local.yaml` names the folder and the file pattern of every release. `config/sources.yaml` is the same list for the test fixtures (`pytest` uses it; do not set `MESHKOR_SOURCES` in the shell when you run the tests).

Rules for a release folder: put all files in it before the first load, and do not add or remove files later. The hash of a folder is the hash of all files in it, so a change makes §3.2 in the verify report fail. A new CMS release gets a new folder.

| Table | Folders |
|---|---|
| 1 `ref_provider` | `NPES` (NPPES October 2026 + deactivation report 20261012) |
| 2 `ref_mpfs`, 14 `ref_anesthesia_cf` | `MPFS2024A`, `MPFS2024B`, `MPFS2024` (2024C), `MPFS2024D`, `MPFS2025A`–`C`, `MPFS2025` (2025D), `MPFS2026A`–`C`, `MPFS` (2026D) |
| 3 `ref_opps` | `OPPS2024A`–`C`, `OPPS2024` (Q4), `OPPS2025A`–`C`, `OPPS2025`, `OPPS2026A`–`C`, `OPPS` |
| 4 `ref_ipps_drg`, `ref_ipps_hospital` | `IPPS/FY2025`, `IPPS/FY2026`, `IPPS/FY2027` |
| 5 `ref_asc` | `ASC2024A`–`C`, `ASC2024`, `ASC2025A`–`C`, `ASC2025`, `ASC2026A`–`C`, `ASC` |
| 6 `ref_ncci_ptp` | `NCCI/PTP` (8 zips, v323r0) |
| 6 `ref_mue` | `MUE2024A`–`C`, `MUE2024`, `MUE2025A`–`C`, `MUE2025`, `MUE2026A`–`C` (each with `hospital` and `practitioner`), `NCCI/...-10-01-2026` |
| 7 `ref_hcris` | `HCRIS/HOSP10FY2023` … `HCRIS/HOSP10FY2026` |
| 8 `ref_ccn_npi` | `ENROLLMENTS` (Hospital Enrollments 2026-07-31) |
| 9 `ref_code_specialty` | `UTILIZATION` (CY2024 by provider and service) |
| 11 `ref_clfs` | `CLFS/2024Q1` … `CLFS/2026Q4` |
| 12 `ref_dmepos`, `ref_dmepos_rural_zip` | `DMEPOS/2024A` … `DMEPOS/2026D` |
| 13 `ref_ambulance`, `ref_zip_locality` | `AMBULANCE/2024`, `AMBULANCE/2025`, `AMBULANCE/2026`, `ZIPLOC/2026` |
| 14 `ref_anesthesia_base_units` | `ANESTHESIA` |

The full list with the CMS page of each release is in the project doc `meshkor-step1-download-list.md`.

## 4. Commands

```bash
python backend/manage.py load_ref all                 # or: load_ref ref_mpfs ref_asc
python backend/manage.py load_ref ref_mpfs --period 2026D
python backend/manage.py build_duckdb                 # rebuild data/meshkor.duckdb from Parquet
python backend/manage.py verify_step1                 # Spec §8 checks → data/reports/verify_latest.md
python backend/manage.py step1_status                 # latest run per table
python backend/manage.py runserver                    # admin at http://localhost:8000/admin/
```

The same steps also run without Django: `python -m pipeline.runner all`, `python -m pipeline.duckdb_build`, `python -m pipeline.verify`.

Only `build_duckdb` writes to the DuckDB file. It builds a new file and then swaps it in. Close any DuckDB session that has `meshkor.duckdb` open before you run it (Windows locks open files).

## 4b. Data register (Excel)

`python register.py` builds `data_register.xlsx`: Summary (counts, GB, free disk), Releases (every configured release: raw present, rows loaded, hash, CMS page), Planned (downloads not configured yet, from `config/register_planned.yaml`), Parquet (every table), Files (every raw file and the table that uses it). Run it after every download and every load. Type your own rows in the sheets "Download log" and "Notes"; they are kept when the file is rebuilt.

## 5. Review loop (no need to send the large files)

1. Put each new release in its own new folder in the raw folder (section 3) and add it to `config/sources_local.yaml`.
2. Run `load_ref all`, then `build_duckdb`, then `verify_step1`.
3. Send **`data/reports/verify_latest.md`**. It contains row counts, hashes, test results and the load warnings. It does not contain provider rows.
4. If a loader stops on a column it cannot find, send the error line and the first 1,000 rows of that file.

## 6. Query examples (DuckDB CLI or Python)

```sql
-- Spec §8.3: one query, five codes, every Step 1 rate (Ohio locality by default)
SELECT * FROM code_profile(DATE '2026-11-15')
WHERE hcpcs IN ('99214','45378','29881','73721','27447');

-- Physician fee schedule on a date of service (defaults: carrier 15202, locality 00, no modifier)
SELECT * FROM mpfs_rate('99214', DATE '2026-11-15');
SELECT * FROM mpfs_rate('73721', DATE '2026-11-15', p_modifier := '26');

-- NCCI edits in effect on a date of service
SELECT * FROM ncci_pairs_on_date('29881', DATE '2026-11-15', p_setting := 'hospital');

-- Spec §8.4: DRG 470 at one hospital (CCN), FY2027
SELECT * FROM ipps_payment('470', DATE '2026-11-15', '360051');

-- Table 10: Medicare drug payment limit (ASP + 6 %) per HCPCS unit, and an NDC package priced in HCPCS units
SELECT * FROM asp_price('J9271', DATE '2026-11-15');
SELECT * FROM ndc_asp('00006302602', DATE '2026-11-15');
SELECT * FROM hcpcs_info('J9271', DATE '2026-11-15');   -- name, status, dose unit

-- Spec §4 first market (Ohio + border zip3 from config/geography.yaml)
SELECT market_part, metro, count(*) FROM v_provider_first_market GROUP BY ALL;
```

## 7. What each loader does

| Table | Main rules |
|---|---|
| `ref_provider` | Primary taxonomy = slot with switch `Y` (not slot 1); if none, slot 1 and `primary_flag_missing`. Deactivated NPIs kept (main file + monthly report). Practice-location state/zip3. CCN candidates from "Other Provider Identifier" type 06. `effective_start/end` = enumeration / deactivation date. Partitioned by state. Batched, so memory stays flat. |
| `ref_mpfs` | CMS no longer posts a dollar file per locality, so the loader calculates it from each RVU release (2024A–2026D): (work RVU × work GPCI + PE RVU × PE GPCI + MP RVU × MP GPCI) × CF, for every code × modifier × locality (about 2.1 M rows per quarter). Output is the folder `data/ref/ref_mpfs/`, one Parquet file per quarter. Rate is null where the file marks the setting NA, or the status is not payable (A, R, T). Imaging codes are capped at the OPPSCAP amount. |
| `ref_mpfs_locality` | Locality → counties (26LOCCO). |
| `ref_opps` | Addendum B national rate, SI, APC, weight, copays. Wage adjustment is the `opps_wage_adjusted` macro (needs table 4). |
| `ref_asc` | Addenda AA + BB, payment-indicator meanings from DD1. Reads `.csv` and the tab-separated `.txt` files of January and July 2024. |
| `ref_ncci_ptp` | Both settings, all parts. Deleted edits kept. Row-level `effective_start` = edit effective date, `effective_end` = deletion date. |
| `ref_mue` | Both settings, MUE value, adjudication indicator and rationale. |
| `ref_hcris` | One row per cost report: CCN, NPI, state, facility type, FY dates, total costs, total charges, hospital-wide cost-to-charge ratio, beds. `is_primary` marks the report to use when one period is filed twice. |
| `ref_anesthesia_cf` | Anesthesia CF per locality (non-QP standard, QP kept for reference). |
| `ref_ipps_drg` | MS-DRG weights from the correction-notice Table 5 (10% cap applied), titles, GMLOS/AMLOS. FY runs Oct 1 – Sep 30. |
| `ref_ccn_npi` | All CCN–NPI pairs: main NPI per Hospital Enrollment, the Additional NPIs file, NPPES other identifiers (type 05/06), and NPPES hospital NPIs (taxonomy 28*) at the same zip + street address (`address_zip`) or the same legal/DBA name (`name_zip`, or `name_city` for a wrong zip) as an enrollment, plus reviewed pairs from `config/ccn_npi_manual.csv` (`manual`, only rows with approved = Y). The verify report puts each Ohio hospital NPI in a category (`federal`, `not_hospital`, `stale`, `hospital`); the < 5 % target counts the `hospital` NPIs. It also writes `data/reports/ccn_npi_ohio_suggestions.csv` with likely CCNs to review. `match_source` says which. Leading zeros of CCNs restored. Verify reports Ohio 282N* hospital NPIs with no CCN (target < 5 % for acute care) and writes the list to `data/reports/ccn_npi_ohio_unmatched.csv`. |
| `ref_code_specialty` | One row per code × Medicare specialty × NPPES taxonomy, from CY2024 utilization. `plausible` = specialty has ≥ 1 % of national services for the code or is in the top 10 (`min_share`, `top_n` in `config/sources.yaml`). Query: `specialty_plausible('27447')`. 10 spot checks in the verify report. No CPT descriptions stored. |
| `ref_clfs` | Lab fee schedule national limit per HCPCS + modifier (`clfs_rate()`). The rate column is `RATE` or, in CY2024 Q1–Q3, `RATE2024`. |
| `ref_dmepos`, `ref_dmepos_rural_zip` | DMEPOS fee per HCPCS × modifiers × state, non-rural and rural; `dmepos_fee(code, dos, state, p_zip)` picks the rural fee for a rural zip. |
| `ref_ambulance`, `ref_zip_locality` | Ambulance amounts per carrier × locality × HCPCS (urban, rural, super rural, rural miles 1–17); `ambulance_rate(code, dos, zip)` uses the zip's rural indicator. |
| `ref_anesthesia_base_units` | Base units per anesthesia code; `anesthesia_payment(code, minutes, dos)` = (base + minutes / 15) × CF. |
| `ref_ipps_hospital` | One row per CCN from the correction-notice Impact File: wage index, COLA, GAF, IME, DSH, uncompensated care, VBP/readmission proxies, quality/EHR flags. Adds the national rates from Tables 1A/1B/1D (set in `config/sources.yaml`), picked by wage index and quality/EHR status, and `operating_base_rate` = labor x wage index + nonlabor x COLA. |

| `ref_asp` | Table 10a. One row per HCPCS per quarter from the ASP Pricing File (2026: "Medicare Part B Payment Limit File"), plus NOC drugs (no code, `price_type = 'NOC'`, 2024–2025). Reads only the Section 508 CSV in each quarter folder `ASP/<yyyy>Q<n>`; finds the header under the note lines; stops if the "Effective …" line names another quarter than the folder. Dates = the quarter. `payment_limit` is per HCPCS unit (`dosage`). |
| `ref_ndc_hcpcs` | Table 10b. The 5 crosswalks (ASP, OPPS, AWP, NOC, PrEP) per quarter. Header names differ by year (`_2024_CODE` / `_2026_CODE`, `NDC2` / `NDC`); a map in `pipeline/ref/_asp_common.py` handles them, and an unknown header stops the load. `ndc11` = NDC without dashes (NULL for skin-substitute product IDs that are not NDCs). `bill_units_pkg` = HCPCS units per package. |
| `ref_hcpcs_code` | HCPCS Level II quarterly file (folders `HCPCS/<yyyy>Q<n>`), 2024Q1–2026Q4. Reads the ANWEB `.xlsx` (skips the transaction and corrections reports). One row per code or modifier per quarter: long/short name, pricing indicator, coverage, BETOS, TOS, added / action / termination dates. `dose_from_description` = the unit in a drug descriptor ("1 mg"); found for about 92 % of J-codes. No CPT/CDT codes are in this file. |

## 8. Known gaps and assumptions (confirm before sign-off)

1. **History (Spec §2, §8.5): complete for 2024–2026.** Quarterly tables (MPFS, OPPS, ASC, MUE, CLFS, DMEPOS, DMEPOS rural zip, anesthesia CF) have all 12 quarters, Q1 2024 to Q4 2026. IPPS has FY2025–FY2027, HCRIS FY2023–FY2026, ambulance CY2024–CY2026. A date before 2024-01-01 returns no rate.
2. **NPPES history.** CMS posts only the current full file. 2024–2025 come from the current file + deactivation report; monthly snapshots start now (Spec §6).
3. **NCCI PTP** has one release (v323r0, Q4 2026). It holds every edit with its effective and deletion dates, so date queries work for 2024–2026. The deletion date is treated as the last day the edit applies (inclusive). Modifier-indicator 9 rows (deletion date = effective date) are marked `is_applicable = false` and left out of the date queries.
4. **Zip to carrier locality, 2026.** CMS posts only the latest 2026 file (`zplc_oct2026`, updated 08/13/2026). It is used for Jan–Sep 2026 (release `2026-08`); the October 2026 ZIP5 file covers Oct–Dec 2026. 2024 and 2025 use the CMS end-of-year files for the full year.
5. **HCRIS.** Cost-to-charge ratio = Worksheet C Part I, line 202, column 5 ÷ column 8 (set in `config/sources.yaml`), hospital-wide only (Spec §6). FY2026 has 22 reports because hospitals are still filing. The NPI column in the RPT file is empty, so table 8 does not use it.
6. **IPPS.** FY2025 uses the interim final action impact file (court decision on the low wage index policy) and the correction-notice Table 5; FY2026 the final rule; FY2027 the correction notice. `ipps_payment()` gives the wage-adjusted operating amount (the §8.4 answer) and an estimate with IME, DSH, uncompensated care, VBP/readmission proxies, low-volume factor and capital. It leaves out outliers, transfers, new-technology add-ons and SCH/MDH hospital-specific rates.
7. **Code specialty** uses CY2024 utilization (the data lags about 2 years; Spec §6 allows this).
8. **Anesthesia base units** come from the CY 2022 file. CMS states they did not change for 2024–2026, so that release is open-ended.
9. **CCN–NPI match (target < 5 %): 1 of 253 Ohio acute-care hospital NPIs without a CCN (0.4 %).** 21 pairs come from `config/ccn_npi_manual.csv` (approved = Y, with a note); 13 NPIs are in `config/ccn_npi_reclass.csv` with a category (closed, not_acute, not_hospital), a reason and a source. Rows marked "confirm" should be checked by someone who knows the Ohio hospitals. The reclass file changes only the category in `v_ccn_npi_ohio_report`.
10. **Licensing (Spec §10).** Descriptions are stored only for HCPCS Level II codes. CPT (AMA) and CDT (ADA) descriptions are dropped. A test checks this.
11. **Layout differences from Spec §3 and §7.** Raw files are in `D:\Datasetof CMS` (set by `MESHKOR_RAW_DIR`), not in `data/raw/`; the hash of each file or folder is in the manifests and in the verify report (§8.7). `ref_mpfs` and `ref_provider` are Parquet folders (one file per quarter / per state), not one file.
12. **Not built yet:** §11 tables 15, 16 (PDF fee tables), 18 (IDR) and 22 (hospital price file catalog).
13. **Spec §11 loaders (tables 17, 19, 20, 21).** `ref_geo` (HUD ZIP-COUNTY / ZIP-CBSA, 2024 Q1 – 2026 Q2; 2026 Q3 not released by HUD yet), `ref_geo_zcta_county` (Census 2020), `ref_quality_hospital` / `ref_quality_measure` / `ref_quality_asc` (Care Compare, Sep 30 2026 release), `ref_ownership` / `ref_chow` / `ref_chow_npi` (data.cms.gov, 2026-09-29), `ref_nadac` (2024–2026, dates chained from the price start) and `ref_ndc_product` / `ref_ndc_package` (FDA NDC, Oct 2026). The verify report checks them in its §11 section.

## 9. Sources loaded

Downloaded October 17–19, 2026 from the CMS pages below. The verify report (`data/reports/verify_latest.md`, §8.7) is the live copy of this table, and its §3.2 checks that no raw file changed since its load. The manifests in `data/ref/_manifest/` hold the full SHA-256, file members, size and load time.

Verify result on 2026-10-19: **180 pass, 0 fail, 1 not run (table 10, optional).**

| Table | Release | File / folder (under `D:\Datasetof CMS`) | SHA-256 (first 16) | Loaded | CMS page |
|---|---|---|---|---|---|
| ref_ambulance | CY2024 | AMBULANCE/2024 | 41f8221a775cac3d | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance/ambulance-fee-schedule-public-use-files |
| ref_ambulance | CY2025 | AMBULANCE/2025 | c1dbbdba39fe2eb2 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance/ambulance-fee-schedule-public-use-files |
| ref_ambulance | CY2026 | AMBULANCE/2026 | 41658147eac5a162 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance/ambulance-fee-schedule-public-use-files |
| ref_anesthesia_base_units | CY2022 | ANESTHESIA | 9bf71b437a1061b1 | 2026-10-18 | https://www.cms.gov/medicare/payment/fee-schedules/physician/anesthesiologists-center |
| ref_anesthesia_cf | 2024A | MPFS2024A | 55c3fb57e2377f7b | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24a |
| ref_anesthesia_cf | 2024B | MPFS2024B | b6ba19357dca0565 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24b |
| ref_anesthesia_cf | 2024C | MPFS2024 | 6f333a2f554ee30c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24c |
| ref_anesthesia_cf | 2024D | MPFS2024D | 2604538d8f6b8265 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24d |
| ref_anesthesia_cf | 2025A | MPFS2025A | 8bc4c67526656b78 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25a |
| ref_anesthesia_cf | 2025B | MPFS2025B | 1fff318c974812d9 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25b |
| ref_anesthesia_cf | 2025C | MPFS2025C | c50de068a8263312 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25c |
| ref_anesthesia_cf | 2025D | MPFS2025 | 5f5c944453462828 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25d-0 |
| ref_anesthesia_cf | 2026A | MPFS2026A | 6eacf966b1e740d9 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26a |
| ref_anesthesia_cf | 2026B | MPFS2026B | 8aea553288e44804 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26b |
| ref_anesthesia_cf | 2026C | MPFS2026C | c7fe4e5b4bbb9499 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26c |
| ref_anesthesia_cf | 2026D | MPFS | 51afbeb853bce73c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26d |
| ref_asc | 2024Q1 | ASC2024A | 2608a7ca655217f9 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2024Q2 | ASC2024B | 00b7a5125f6e40ff | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2024Q3 | ASC2024C | 8ac759d830f72cda | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2024Q4 | ASC2024 | 33b68627f4886baa | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2025Q1 | ASC2025A | 8c57e464f81c2091 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2025Q2 | ASC2025B | 92c35a8b7e6211e8 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2025Q3 | ASC2025C | f83806c69a3a35e1 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2025Q4 | ASC2025 | 265ebba2496d31ca | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2026Q1 | ASC2026A | 51f77275e93877a9 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2026Q2 | ASC2026B | 74ccae7b4005208f | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2026Q3 | ASC2026C | 833cb837897eb290 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2026Q4 | ASC | af16cc05f7a46296 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_ccn_npi | 2026-07 | ENROLLMENTS | c09f7db4dfbc2e8a | 2026-10-19 | https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/hospital-enrollments |
| ref_clfs | 2024Q1 | CLFS/2024Q1 | 180b90dff4386b2e | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/24clabq1 |
| ref_clfs | 2024Q2 | CLFS/2024Q2 | d178ce7cd501885b | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/24clabq2 |
| ref_clfs | 2024Q3 | CLFS/2024Q3 | c4d9c87d8edbcd8f | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/24clabq3 |
| ref_clfs | 2024Q4 | CLFS/2024Q4 | a95268fa972965ef | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/24clabq4 |
| ref_clfs | 2025Q1 | CLFS/2025Q1 | 3a6ae381501ee77a | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/25clabq1 |
| ref_clfs | 2025Q2 | CLFS/2025Q2 | 97b70c0d1b46d71c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/25clabq2 |
| ref_clfs | 2025Q3 | CLFS/2025Q3 | 166efc2b2ddddf11 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/25clabq3 |
| ref_clfs | 2025Q4 | CLFS/2025Q4 | f133417147f4c942 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/25clabq4 |
| ref_clfs | 2026Q1 | CLFS/2026Q1 | 5be760b9fc8660c5 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/26clabq1 |
| ref_clfs | 2026Q2 | CLFS/2026Q2 | 43c81064de5bf84a | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/26clabq2 |
| ref_clfs | 2026Q3 | CLFS/2026Q3 | 179e916d69121b89 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/26clabq3 |
| ref_clfs | 2026Q4 | CLFS/2026Q4 | 36e3ee8769971686 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/26clabq4 |
| ref_code_specialty | CY2024 | UTILIZATION | 0893456869f155e0 | 2026-10-18 | https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service |
| ref_dmepos | 2024A | DMEPOS/2024A | a8c8018778cebb5e | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-a |
| ref_dmepos | 2024B | DMEPOS/2024B | 52997b1ee2bf8e83 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-b |
| ref_dmepos | 2024C | DMEPOS/2024C | 77ee941845a5a23a | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-c |
| ref_dmepos | 2024D | DMEPOS/2024D | bab7fd9782ea6604 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-d |
| ref_dmepos | 2025A | DMEPOS/2025A | 9c9d9d0584b1ee9c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-a |
| ref_dmepos | 2025B | DMEPOS/2025B | 33454976cd03f9cd | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-b |
| ref_dmepos | 2025C | DMEPOS/2025C | 8005fbc76747ae80 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-c |
| ref_dmepos | 2025D | DMEPOS/2025D | e0fbe6dcdb1c76ac | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-d |
| ref_dmepos | 2026A | DMEPOS/2026A | ba175cc113bf2a57 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-a |
| ref_dmepos | 2026B | DMEPOS/2026B | 5b65b9f15a0c6f55 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-b |
| ref_dmepos | 2026C | DMEPOS/2026C | d367d30b6d036dfe | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-c |
| ref_dmepos | 2026D | DMEPOS/2026D | b87e69dda8d536c7 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-d |
| ref_dmepos_rural_zip | 2024A | DMEPOS/2024A | a8c8018778cebb5e | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-a |
| ref_dmepos_rural_zip | 2024B | DMEPOS/2024B | 52997b1ee2bf8e83 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-b |
| ref_dmepos_rural_zip | 2024C | DMEPOS/2024C | 77ee941845a5a23a | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-c |
| ref_dmepos_rural_zip | 2024D | DMEPOS/2024D | bab7fd9782ea6604 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-d |
| ref_dmepos_rural_zip | 2025A | DMEPOS/2025A | 9c9d9d0584b1ee9c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-a |
| ref_dmepos_rural_zip | 2025B | DMEPOS/2025B | 33454976cd03f9cd | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-b |
| ref_dmepos_rural_zip | 2025C | DMEPOS/2025C | 8005fbc76747ae80 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-c |
| ref_dmepos_rural_zip | 2025D | DMEPOS/2025D | e0fbe6dcdb1c76ac | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-d |
| ref_dmepos_rural_zip | 2026A | DMEPOS/2026A | ba175cc113bf2a57 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-a |
| ref_dmepos_rural_zip | 2026B | DMEPOS/2026B | 5b65b9f15a0c6f55 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-b |
| ref_dmepos_rural_zip | 2026C | DMEPOS/2026C | d367d30b6d036dfe | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-c |
| ref_dmepos_rural_zip | 2026D | DMEPOS/2026D | b87e69dda8d536c7 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-d |
| ref_hcris | FY2023 | HCRIS/HOSP10FY2023 | c66a0f1683596338 | 2026-10-17 | https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year |
| ref_hcris | FY2024 | HCRIS/HOSP10FY2024 | f288f704f227c0b2 | 2026-10-17 | https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year |
| ref_hcris | FY2025 | HCRIS/HOSP10FY2025 | 5aca20a2c5d3f540 | 2026-10-17 | https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year |
| ref_hcris | FY2026 | HCRIS/HOSP10FY2026 | de7fbd886285fe67 | 2026-10-17 | https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year |
| ref_ipps_drg | FY2025 | IPPS/FY2025/fy2025-ipps-final-rule-and-correction-notice-table-5.zip | d5e0a0bd231412e1 | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2025-ipps-final-rule-home-page |
| ref_ipps_drg | FY2026 | IPPS/FY2026/cms-1833-f-table-5.zip | 14dba6b8f06ab819 | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2026-ipps-final-rule-home-page |
| ref_ipps_drg | FY2027 | IPPS/FY2027/cms-1849-fr-and-cn-table-5.zip | 3b43654767907b1c | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2027-ipps-final-rule-home-page |
| ref_ipps_hospital | FY2025 | IPPS/FY2025/fy_2025_ipps_impact_file-fr-cn-ifc.zip | 1b650a7f96eef459 | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2025-ipps-final-rule-home-page |
| ref_ipps_hospital | FY2026 | IPPS/FY2026/fy_2026_ipps_final_rule_impact_file.zip | c19ae04778a7018f | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2026-ipps-final-rule-home-page |
| ref_ipps_hospital | FY2027 | IPPS/FY2027/fy-2027-ipps-fr-cn-impact-file.zip | 6e51b1015b6c5c93 | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2027-ipps-final-rule-home-page |
| ref_mpfs | 2024A | MPFS2024A | 55c3fb57e2377f7b | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24a |
| ref_mpfs | 2024B | MPFS2024B | b6ba19357dca0565 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24b |
| ref_mpfs | 2024C | MPFS2024 | 6f333a2f554ee30c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24c |
| ref_mpfs | 2024D | MPFS2024D | 2604538d8f6b8265 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24d |
| ref_mpfs | 2025A | MPFS2025A | 8bc4c67526656b78 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25a |
| ref_mpfs | 2025B | MPFS2025B | 1fff318c974812d9 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25b |
| ref_mpfs | 2025C | MPFS2025C | c50de068a8263312 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25c |
| ref_mpfs | 2025D | MPFS2025 | 5f5c944453462828 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25d-0 |
| ref_mpfs | 2026A | MPFS2026A | 6eacf966b1e740d9 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26a |
| ref_mpfs | 2026B | MPFS2026B | 8aea553288e44804 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26b |
| ref_mpfs | 2026C | MPFS2026C | c7fe4e5b4bbb9499 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26c |
| ref_mpfs | 2026D | MPFS | 51afbeb853bce73c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26d |
| ref_mpfs_locality | 2026D | MPFS | 51afbeb853bce73c | 2026-10-17 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26d |
| ref_mue | 2024Q1/hospital | MUE2024A/hospital | 76d6075fc988e138 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q1/practitioner | MUE2024A/practitioner | 2d670114795fa732 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q2/hospital | MUE2024B/hospital | 19b60926d0e1d6ec | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q2/practitioner | MUE2024B/practitioner | 4478e01e6208ca8b | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q3/hospital | MUE2024C/hospital | 65098cb1292d498f | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q3/practitioner | MUE2024C/practitioner | 06b9378e968b349c | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q4/hospital | MUE2024/hospital | 58da99490a301a85 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q4/practitioner | MUE2024/practitioner | 4205f956af329093 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q1/hospital | MUE2025A/hospital | aafdacf073fd63e9 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q1/practitioner | MUE2025A/practitioner | 86ce15fce2cd42ec | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q2/hospital | MUE2025B/hospital | 3097c3df389807f3 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q2/practitioner | MUE2025B/practitioner | fb97746498c8166c | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q3/hospital | MUE2025C/hospital | 35ae92a8e89f9ad0 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q3/practitioner | MUE2025C/practitioner | 1679c026f8a8cbec | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q4/hospital | MUE2025/hospital | 5a6593e69c8fba7b | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q4/practitioner | MUE2025/practitioner | 90acec749e1f03f5 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q1/hospital | MUE2026A/hospital | 0ffee7f6d05a694c | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q1/practitioner | MUE2026A/practitioner | 96543e747e763d72 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q2/hospital | MUE2026B/hospital | 79a93446622b2582 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q2/practitioner | MUE2026B/practitioner | 2e504c35d76c301c | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q3/hospital | MUE2026C/hospital | 49a57f35234feeea | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q3/practitioner | MUE2026C/practitioner | c3ae164122f0f901 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q4/hospital | NCCI/facilityoutpatienthospitalservicesmuetable-effective-10-01-2026 | f174b39ddcaf08fe | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edits |
| ref_mue | 2026Q4/practitioner | NCCI/practitionerservicesmuetable-effective-10-01-2026 | e165bcd1e39ee0db | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edits |
| ref_ncci_ptp | 2026Q4/hospital | NCCI/PTP/ccioph-v323r0-f1.zip | fdf7651190e17f60 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/hospital | NCCI/PTP/ccioph-v323r0-f2.zip | 5f39fb6295824ad7 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/hospital | NCCI/PTP/ccioph-v323r0-f3.zip | e323c7c723c9a8ba | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/hospital | NCCI/PTP/ccioph-v323r0-f4.zip | 0e731c4c0f5a2150 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/practitioner | NCCI/PTP/ccipra-v323r0-f1.zip | 40adc15de0b5cf94 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/practitioner | NCCI/PTP/ccipra-v323r0-f2.zip | e0c916cc5b0bf1b7 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/practitioner | NCCI/PTP/ccipra-v323r0-f3.zip | 79024324e5f2ac96 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/practitioner | NCCI/PTP/ccipra-v323r0-f4.zip | 028a6d91e27ab177 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_opps | 2024Q1 | OPPS2024A | cd0094a6114f2d05 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2024Q2 | OPPS2024B | 4175fce3d363bd24 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2024Q3 | OPPS2024C | 0f51593ebf1f2f07 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2024Q4 | OPPS2024 | a5500da0c2ce1066 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient/addendum-a-b-updates/october-2024-updated-10/02/2024-0 |
| ref_opps | 2025Q1 | OPPS2025A | 5f7ed650a467ce9e | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2025Q2 | OPPS2025B | 033b02a032543976 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2025Q3 | OPPS2025C | 296e0e00061a0379 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2025Q4 | OPPS2025 | c044636bbb871017 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates/october-2025-addendum-b |
| ref_opps | 2026Q1 | OPPS2026A | 7a15f0ecd0280cd3 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2026Q2 | OPPS2026B | 25b666a7023c190b | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2026Q3 | OPPS2026C | 8dc631d3dce30ee3 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2026Q4 | OPPS | 0b2483f46bd2fe93 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates/october-2026-addendum-b |
| ref_provider | 2026-10 | NPES | b22e2fac1cef4575 | 2026-10-17 | https://download.cms.gov/nppes/NPI_Files.html |
| ref_provider | 2026-10 | NPES/NPPES Deactivated NPI Report 20261012.xlsx | 0552b3192932726c | 2026-10-17 | https://download.cms.gov/nppes/NPI_Files.html |
| ref_zip_locality | 2024EOY | AMBULANCE/2024 | 41f8221a775cac3d | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance |
| ref_zip_locality | 2025EOY | AMBULANCE/2025 | c1dbbdba39fe2eb2 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance |
| ref_zip_locality | 2026-08 | ZIPLOC/2026 | a2060fccf48a1bed | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules |
| ref_zip_locality | 2026Q4 | AMBULANCE/2026 | 41658147eac5a162 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance |
