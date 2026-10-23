# Hospital price files: progress (2026-10-23 12:21 UTC)

**2 of 4 hospitals loaded, 2 remaining.**  (run `python -m pipeline.hpt.hospitals` to get the full Ohio list; this counts only hospital_sites.csv)

| Stage | Hospitals |
|---|---|
| 0 no website | 0 |
| 1 website known | 2 |
| 2 file URL found | 0 |
| 3 downloaded | 0 |
| 4 loaded | 2 |
| 5 verified | 0 |

| Disk | Size |
|---|---|
| raw files `D:\Meshkor_Backend\meshkor-data\data\raw\MRF` | 0.0 GB |
| Parquet `D:\Meshkor_Backend\meshkor-data\data\ref\ref_hospital_mrf` | 0.04 GB |
| DuckDB | 1.63 GB |

## Per hospital

| Tier | CCN | Hospital | System | Stage | Downloaded | Loaded (rows) | File dated | Verify | Raw MB | Website / file URL |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 360085 | Ohio State University Hospitals | OSU Wexner | 4 loaded |  | 2026-10 (2,366,510) | 2026-07-01 |  | 0.0 | https://wexnermedical.osu.edu |
| 1 | 360242 | Arthur G James Cancer Hospital | OSU Wexner | 4 loaded |  | 2026-10 (4,470,209) | 2026-07-01 |  | 0.0 | https://wexnermedical.osu.edu |
| 1 | 360051 | Miami Valley Hospital | Premier Health | 1 website known |  |  (0) |  |  | 0.0 | https://www.premierhealth.com |
| 1 | 360180 | Cleveland Clinic Hospital | Cleveland Clinic | 1 website known |  |  (0) |  |  | 0.0 | https://my.clevelandclinic.org |

## Next actions

- Stage 1 → run discover (or open <website>/cms-hpt.txt in the browser): 360051 Miami Valley Hospital; 360180 Cleveland Clinic Hospital
