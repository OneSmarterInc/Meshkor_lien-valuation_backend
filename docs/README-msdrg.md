# MeshKor: MS-DRG definitions, load and verify

Date: October 22, 2026. For lien valuation (inpatient bills). Raw folder: `E:\Hansavahini\Datasetof CMS\MSDRG\V41` … `V44`.

## What the folder holds

Each version folder has two kinds of file from the CMS MS-DRG page:

| File | What | Loaded? |
|---|---|---|
| `appendix_A.txt` | List of every MS-DRG: number, MDC, medical/surgical, title | Yes → `ref_msdrg` |
| `appendix_B.txt` | Every ICD-10-CM diagnosis → MDC → DRG range | Yes → `ref_msdrg_dx` |
| `appendix_C.txt` | Every CC and MCC diagnosis, with the principal-diagnosis exclusion group; part 3 lists DRG-specific exclusions | Yes → `ref_msdrg_cc`, `ref_msdrg_cc_excl` |
| `appendix_D_E.txt`, `appendix_F_I.txt`, `mdcs_*.txt` | The grouping logic as prose and tables | Hashed, not parsed (the grouper software does this) |
| `*java*jars*.zip`, `standalone-jars.zip` | **CMS's official MS-DRG grouper and Medicare Code Editor, as Java jars** | Hashed, recorded in the manifest as "grouper software" |

The grouper jar is the important find. To value an inpatient bill by DRG, give the jar the diagnoses, procedures, age, sex and discharge status from the UB-04; it returns the DRG. There is no need to rebuild the rules in appendices D–I. Running it needs Java on the build PC; that is a later step.

## Versions and dates

| Version | Fiscal year | In force |
|---|---|---|
| V41 | FY2024 | 2023-10-01 → 2024-03-31 |
| V41.1 | FY2024 | 2024-04-01 → 2024-09-30 |
| V42 | FY2025 | 2024-10-01 → 2025-03-31 |
| V42.1 | FY2025 | 2025-04-01 → 2025-09-30 |
| V43 | FY2026 | 2025-10-01 → 2026-03-31 |
| V43.1 | FY2026 | 2026-04-01 → 2026-09-30 |
| V44 | FY2027 | 2026-10-01 → 2027-09-30 |

The `.1` versions are the April code updates. Every date of service from October 2023 on maps to exactly one version.

## Files (put all 4 in `D:\meshkor-data`)

| File | Does |
|---|---|
| `load_msdrg.py` | Parses appendices A, B, C of every version folder into 4 Parquet tables with lineage; writes one manifest per version with the SHA-256 of every file, jars included. 10 seconds for all 7. |
| `verify_msdrg.py` | 22 checks per version (154 total): raw hashes unchanged, row counts recounted from the text files, no duplicate DRG, every DRG in appendix B exists in A, CC levels valid, golden titles for DRG 470 / 291 / 871, DRG count equals `ref_ipps_drg` Table 5 for the same fiscal year. |
| `views_msdrg.sql` | DuckDB views and macros `msdrg_title()`, `msdrg_for_dx()`, `msdrg_cc_level()`. |
| `register_msdrg.py` | Adds each version to `data_register.xlsx` (Download log + "MS-DRG" sheet). Skips versions already there. |

## Commands

```powershell
cd D:\meshkor-data
.venv\Scripts\activate
python load_msdrg.py     --raw "E:\Hansavahini\Datasetof CMS\MSDRG"
python verify_msdrg.py
python register_msdrg.py --who Hansavahini
```

Expected: 7 versions, `ref_msdrg` 766–773 rows each, `ref_msdrg_dx` ~88,000, `ref_msdrg_cc` ~18,300; then `154 pass, 0 fail` (plus 4 IPPS cross-checks on the build PC).

Then paste `views_msdrg.sql` into `sql\views.sql`, or run it once by hand as with `views_mrf.sql`.

## Tables

| Table | One row per | Columns |
|---|---|---|
| `ref_msdrg` | DRG × version | `ms_drg`, `mdc`, `drg_type` (MED/SURG), `title`, `fiscal_year` |
| `ref_msdrg_dx` | diagnosis × MDC × DRG range × version | `icd10`, `mdc`, `drg_from`, `drg_to`, `description` |
| `ref_msdrg_cc` | CC/MCC diagnosis × version | `icd10`, `cc_level` (CC/MCC), `hac`, `pdx_exclusion_group`, `pdx_exclusion_count`, `cc_only_if_alive`, `description` |
| `ref_msdrg_cc_excl` | DRG group × excluded diagnosis × version | `mdc`, `drg_from`, `drg_to`, `drg_group_title`, `icd10`, `description` (V42 onward; V41 has no part 3) |

All carry `effective_start`, `effective_end`, `source_file`, `source_sha256`, `period` (= version).

## Queries

```sql
SELECT * FROM msdrg_title('470', DATE '2026-05-01');          -- title, MDC, type, version in force
SELECT * FROM msdrg_for_dx('S72001A', DATE '2026-05-01');     -- hip fracture -> candidate DRGs 521/522/535/536
SELECT * FROM msdrg_cc_level('I5023', DATE '2026-05-01');     -- MCC
SELECT period, count(*) FROM ref_msdrg GROUP BY 1 ORDER BY 1;
```

## How the lien report uses this

1. The UB-04 shows the DRG the hospital billed. `msdrg_title()` gives its name for the report, and `ipps_payment(drg, dos, ccn)` (already built) gives the Medicare payment.
2. When the bill shows diagnoses but no DRG, `msdrg_for_dx()` narrows the candidates, and the grouper jar (later) settles it.
3. `msdrg_cc_level()` explains why a stay landed in the "with MCC" DRG, which matters when a hospital's DRG choice is challenged.

## Next version

CMS posts V45 in August 2027. Make `MSDRG\V45`, put the definitions zip and the jar zip in it, extract the text files next to the zip, add `"V45": ("2027-10-01", "2028-09-30", "FY2028")` to `VERSIONS` in `load_msdrg.py`, run the 3 commands.
