# MeshKor Step 2: hospital price files, load and verify

Date: October 22, 2026. First file: Ohio State University Hospitals, CCN 360085.

## Files (put all 4 in `D:\meshkor-data`)

| File | Does |
|---|---|
| `load_mrf.py` | Reads one hospital's CMS tall CSV (template v2.x or v3.x), writes Parquet with the 5 lineage columns, writes a manifest with SHA-256. |
| `verify_mrf.py` | 15 checks: raw hash unchanged, rows parquet = rows csv, lineage filled, codes mapped, first and last record match. Writes `data\reports\verify_mrf_<ccn>_<period>.md`. |
| `views_mrf.sql` | DuckDB view `ref_hospital_mrf`, macros `mrf_rate()` and `mrf_drg()`, view `v_mrf_drugs`. |
| `register_mrf.py` | Adds the file to `data_register.xlsx` (sheets Download log and Hospital MRF). Skips a file already there. |

## Commands (OSU)

```powershell
cd D:\meshkor-data
.venv\Scripts\activate
pip install duckdb openpyxl          # once

python load_mrf.py --ccn 360085 --period 2026-10 `
  --raw "E:\Hansavahini\Datasetof CMS\MRF\2026-10\360085" `
  --page https://wexnermedical.osu.edu/patient-and-visitor-guide/patient-pricing-lists

python verify_mrf.py --ccn 360085 --period 2026-10

python register_mrf.py --ccn 360085 --period 2026-10 --who Hansavahini
```

Expected: `OK rows=2,366,510 payers=26`, then `15 pass, 0 fail`.

## Make it queryable in DuckDB

Paste the contents of `views_mrf.sql` at the end of `sql\views.sql`, then `python backend\manage.py build_duckdb`. Until then, run it once by hand:

```powershell
python -c "import duckdb; c=duckdb.connect('data/meshkor.duckdb'); c.execute(open('views_mrf.sql').read()); print(c.execute('SELECT ccn, period, count(*) FROM ref_hospital_mrf GROUP BY ALL').fetchall())"
```

Then:

```sql
SELECT * FROM mrf_rate('360085', '27447', DATE '2026-09-01') ORDER BY negotiated_dollar;
SELECT * FROM mrf_drg('360085', '470', DATE '2026-09-01');
SELECT hcpcs, payer_name, negotiated_dollar FROM v_mrf_drugs WHERE ccn = '360085' AND hcpcs = 'J9299';
```

## Output layout

```
data\ref\ref_hospital_mrf\ccn=360085\period=2026-10\part-000.parquet     13 MB (ZSTD), 2,366,510 rows
data\ref\_manifest\ref_hospital_mrf\360085_2026-10.json                   sources, hashes, rows, warnings
data\work\31-1340739_…standardcharges.utf8.csv                            cleaned copy (see note), can be deleted
data\reports\verify_mrf_360085_2026-10.md
```

Each new hospital or month is one more `ccn=…\period=…` folder. Re-running a load replaces only that folder.

## Table `ref_hospital_mrf`

| Column | From CMS column | Meaning |
|---|---|---|
| `ccn`, `hospital_name`, `ein`, `type2_npis`, `mrf_version`, `last_updated_on` | file header rows | Hospital block. `ein` is the number in the file name. |
| `description` | description | Hospital's own line text (chargemaster text, not AMA text) |
| `code_1..4`, `code_1..4_type` | code\|N, code\|N\|type | Up to 4 codes per line |
| `modifiers`, `setting`, `drug_unit`, `drug_type` | | setting = Inpatient / Outpatient / Both |
| `gross_charge`, `discounted_cash` | standard_charge\|gross, \|discounted_cash | Sticker price, cash price |
| `payer_name`, `plan_name` | | |
| `negotiated_dollar`, `negotiated_percentage`, `negotiated_algorithm`, `estimated_amount` | standard_charge\|negotiated_* | The contract rate, in whichever form the contract uses |
| `median_amount`, `pct_10`, `pct_90`, `rate_count` | median_amount, 10th_percentile, 90th_percentile, count | 2026 percentile fields (filled only for percentage contracts) |
| `methodology`, `charge_min`, `charge_max`, `notes` | | |
| `hcpcs`, `ms_drg`, `apr_drg`, `rc`, `ndc`, `cdm` | derived | The code of each type, pulled out of code_1..4 for joins (CPT and HCPCS both land in `hcpcs`; CDM and LOCAL both in `cdm`) |
| `effective_start`, `effective_end`, `source_file`, `source_sha256`, `period` | lineage | `effective_start` = file's last_updated_on; `effective_end` = 9999-12-31 until a newer file is loaded; `period` = download month |

## Notes on the OSU file

- 108 lines hold stray Windows-1252 bytes (non-breaking spaces, a double-encoded ®). The loader writes a UTF-8 copy to `data\work` and loads that. The raw file is untouched; its hash is what the manifest records. Only description text is affected.
- Some descriptions hold a bare `"` (inch marks). DuckDB reads them with `strict_mode=false`; Python's csv module cannot, which is why verify counts rows through DuckDB.
- `discounted_cash` is empty on every row. OSU posts no cash price in this file. Report it as "not posted", not as zero.
- 30,212 rows are APR-DRG (Medicaid inpatient groups), 32,480 are MS-DRG.
- The attestation column is `True`, signed Beth Carlson, file dated 7/1/2026.

## Next hospitals

Same 3 commands with a new `--ccn`, `--period`, `--raw` and `--page`. If `load_mrf.py` stops with `unmapped columns`, the hospital used a column name outside the CMS template; send the message and I'll add it to `COLMAP`. When the next OSU file arrives (2027), load it as `period=2027-07`; then set `effective_end` of the 2026-10 load to the day before by re-running it with `--effective-end 2027-06-30`.
