# Step 2: hospital price files (Phase 2 of the Developer Guide)

Date: October 23, 2026. Replaces the standalone `load_mrf.py` / `verify_mrf.py` / `register_mrf.py` (delete those three; the table is now a normal pipeline table).

## What this adds to the repo

| Path | Does | Guide |
|---|---|---|
| `pipeline/ref/hospital_mrf.py` | Loader for table `ref_hospital_mrf`, run by `load_ref`. Reads CSV tall, CSV wide and JSON (v2.x, v3.x) into one column set. DuckDB writes each hospital's Parquet part directly, so a 4.5 M-row file loads in 15 s with flat memory. | 2.4 |
| `pipeline/hpt/hospitals.py` | Ohio acute-care hospital list from `ref_provider` × `ref_ccn_npi` × `config/hospital_taxonomies.yaml`, minus `ccn_npi_reclass.csv`, plus websites from `config/hospital_sites.csv` → `data/ref/hpt_hospitals.parquet` | 2.1 |
| `pipeline/hpt/discover.py` | Fetches `/cms-hpt.txt` for every site, matches blocks to CCNs by name → `data/ref/hpt_catalog.parquet` (URL, method, status, contact) | 2.2 |
| `pipeline/hpt/download.py` | Streams every catalogued file to `<raw>\MRF\<period>\<ccn>\`, hashes, skips unchanged files, extracts zips, saves the source page, prints the `sources_local.yaml` lines to add | 2.3 |
| `pipeline/hpt/archive.py` | Wayback CDX search and download of 2024–2025 captures into `MRF\<yyyy-mm>\<ccn>\` with `ARCHIVE.txt` | 2.3 step 4 |
| `pipeline/hpt/quality.py` | Per-hospital quality report `data/reports/hpt_quality_<ccn>_<period>.md` | 2.4 step 4 |
| `pipeline/hpt/verify.py` | 11 checks per hospital × period → `data/reports/verify_hpt.md` | §3.2 / §8.1 |
| `config/payer_groups.yaml` | Regex → cleaned insurer name (`payer_group` column) | 2.4 |
| `config/hospital_taxonomies.yaml`, `config/hospital_sites.csv` | Hospital taxonomies; website per system (fill as you go) | 2.1 |
| `sql/views_step2.sql` + `tools/patch_views_sql.py` | Macros `mrf_rate`, `mrf_rc_rate`, `mrf_drg`, `mrf_rate_summary`, views `v_mrf_drugs`, `v_mrf_coverage`, plus the MS-DRG and 340B macros, each with a `-- @stmt` marker | 3.4 |
| `tests/test_hpt.py` + `tests/fixtures/raw/MRF/` | 9 tests: three layouts, lineage, wide unpivot, JSON, cp1252 fallback, payer groups, `cms-hpt.txt` parser, hospital list | |
| `.gitignore` | Fixed: fixture zips/xlsx are tracked again (the Oct 23 version dropped them, which is why 32 tests fail on a fresh clone) | |

## Install (once)

```powershell
cd D:\Meshkor_Backend\meshkor-data
Expand-Archive "C:\Users\hansa\Downloads\meshkor-phase2.zip" -DestinationPath . -Force      # files land in place
pip install ijson requests
python tools\patch_views_sql.py                                   # repairs sql\views.sql
Remove-Item load_mrf.py, verify_mrf.py, register_mrf.py           # superseded
```

Then paste the `ref_hospital_mrf:` block from `config\sources_hpt_snippet.yaml` into `config\sources_local.yaml` (the two OSU files are already filled in).

## Load the two files you have, rebuild, verify

```powershell
python backend\manage.py load_ref ref_hospital_mrf        # ~30 s for OSU + James
python backend\manage.py build_duckdb
python backend\manage.py verify_step1
python -m pipeline.hpt.verify                              # 22 pass, 0 fail expected
python -m pipeline.hpt.quality --all
python register.py                                         # ref_hospital_mrf now appears as a loaded table
python -m pytest -q                                        # 45 + 9 tests
```

Queries:

```sql
SELECT * FROM v_mrf_coverage;
SELECT * FROM mrf_rate_summary('360085', '99213', DATE '2026-09-01');
SELECT * FROM mrf_drg('360085', '470', DATE '2026-09-01');
SELECT * FROM mrf_rc_rate('360085', '120', DATE '2026-09-01');
```

## Add the other Ohio hospitals (the Phase 2 loop)

```powershell
python -m pipeline.hpt.hospitals                 # list; fill websites in config\hospital_sites.csv, rerun
python -m pipeline.hpt.discover                  # cms-hpt.txt per site -> catalog (use the US VPN for "blocked")
python -m pipeline.hpt.download --period 2026-11 --only 360051,360180     # pilot hospitals first
#   paste the printed release lines into config\sources_local.yaml
python backend\manage.py load_ref ref_hospital_mrf
python backend\manage.py build_duckdb
python -m pipeline.hpt.verify
python -m pipeline.hpt.quality --all
```

Monthly: a Task Scheduler job running `download --period <yyyy-mm>` on the 1st; unchanged files are detected by hash and skipped.

History: `python -m pipeline.hpt.archive --ccn 360085 --list-only`, then without `--list-only` to fetch the months that exist. Archive files are not an official source; the report must say so.

## Table `ref_hospital_mrf`

Same columns as before plus `billing_class`, `payer_notes`, `payer_group`, `attestation`, `source_layout`. One folder per hospital × period under `data\ref\ref_hospital_mrf\<ccn>_<period>\`. `load_ref` rebuilds the whole folder each run (all configured releases), like `ref_mpfs`.

`effective_start` = the release's `effective_start` in the yaml (set it to the file's `last_updated_on`); when a newer file for the same CCN is loaded, set the older release's `effective_end` to the day before the new file's date.

## Two things the first two files taught us

1. **Multipliers posted as dollars.** At OSU, 19 % of rows have a "dollar" rate under $5 on a charge over $50 (for example Cigna 0.62, Medicaid 1.07 on a $238 visit). Those are percentages or multipliers the hospital put in the dollar column. The quality report counts them; the pricing step must treat `negotiated_dollar < 5 AND gross_charge >= 50` as a multiplier, not a payment.
2. **No cash price at OSU or the James.** `discounted_cash` is empty on every row. Report "not posted".

## What is still open in Phase 2

| Item | State |
|---|---|
| Websites for all ~90 Ohio hospitals | `hospital_sites.csv` has 14 systems; `hospitals.py` prints the rest |
| Crawl + download of all hospitals | scripts ready; run with the US VPN, 2–3 hours |
| 2024–2025 history | `archive.py` ready; Member 2 runs it per pilot hospital |
| Wide and JSON parsers | written and tested on synthetic files; first real wide/JSON hospital will tell |
| MS-DRG and 340B in `load_ref` | still the standalone scripts; next patch |
