# verify ref_hospital_mrf

Run 2026-10-27T04:16:26+00:00  Result: **13 pass, 0 fail** over 1 releases

| CCN | Period | Hospital | Pass | Fail | Quarantined |
|---|---|---|---|---|---|
| 360039 | 2026-10 | Genesis Healthcare System | 13 | 0 |  |

| CCN | Period | Check | Result | Detail |
|---|---|---|---|---|
| 360039 | 2026-10 | parquet folder exists | PASS | D:\Meshkor_Backend\meshkor-data\data\ref\ref_hospital_mrf\360039_2026-10 |
| 360039 | 2026-10 | raw folder unchanged | PASS | dc72d51e84989065… |
| 360039 | 2026-10 | parquet has rows | PASS | 1,897,434 |
| 360039 | 2026-10 | rows = manifest | PASS | 1,897,434 = 1,897,434 |
| 360039 | 2026-10 | rows parquet = rows csv | PASS | 1,897,434 = 1,897,434 |
| 360039 | 2026-10 | lineage filled | PASS |  |
| 360039 | 2026-10 | one source hash | PASS |  |
| 360039 | 2026-10 | ccn matches release | PASS |  |
| 360039 | 2026-10 | no negative prices | PASS |  |
| 360039 | 2026-10 | rows without a code <= 2.0 % | PASS | 0 (0.00 %) |
| 360039 | 2026-10 | unmapped code types <= 2.0 % | PASS | 0 (0.00 %) |
| 360039 | 2026-10 | payer_group set on every payer row | PASS |  |
| 360039 | 2026-10 | one hospital name | PASS |  |
