# Hospital price files: the data member's guide (Hansavahini)

Date: October 23, 2026. You download and load hospital price files. Your friend changes code when a file needs it. This page is your whole job, start to finish.

## The one idea

Every Ohio hospital must publish one machine-readable price file (CMS rule) and a small text file `cms-hpt.txt` on its website that says where the price file is. We get the price file, keep it exactly as downloaded (its SHA-256 hash is the proof), load it into the table `ref_hospital_mrf`, check it, and record it. One hospital at a time. The scoreboard `data\reports\hpt_progress.md` always shows done / remaining.

## The automatic run (through your own Chrome, with Urban VPN)

Python has no US address, but your Chrome does (Urban VPN). So the pipeline drives Chrome: it opens each hospital's `cms-hpt.txt` and downloads each price file **inside Chrome**, straight to `E:\`. You watch; you type nothing.

**One-time setup (5 min)**
```powershell
python -m pip install playwright          # the remote control for Chrome; no browser download needed
.\tools\chrome_hpt.ps1                   # opens a dedicated Chrome window (profile D:\Meshkor_Backend\chrome-hpt)
```
In that window, once: Chrome Web Store → install **Urban VPN Proxy** → pin it → choose **United States** → ON. The tab `ipinfo.io/json` must show `"country": "US"`. Leave the window open.

**Every run**
```powershell
.\tools\chrome_hpt.ps1                                        # if the window is not open yet; check VPN = US
python -m pipeline.hpt.run --tier 1 --dry-run                  # lists the CCNs it will do
python -m pipeline.hpt.run --tier 1                            # Miami Valley, Cleveland Clinic (+ OSU/James: unchanged, skipped)
python -m pipeline.hpt.run --tier 2                            # the 15 big systems
python -m pipeline.hpt.run --tier 3                            # the rest
python -m pipeline.hpt.run --all                               # everything with a website, in one go
```
`--period` defaults to this month. `--via auto` (default) tries Python first and switches to Chrome for any hospital that refuses; `--via chrome` sends everything through Chrome.

What one run does, stopping at the first failure: hospitals list → `cms-hpt.txt` per site → download (hash, skip unchanged, log) → release added to `sources_local.yaml` → `load_ref` → `build_duckdb` → `verify` → `quality` → `progress`.

`config\hospital_sites.csv` now lists 56 Ohio systems with their websites and a `name_match` pattern that ties each hospital in the Medicare list to its system. `verified=no` means the website came from general knowledge; `discover` proves it by reading the site's `cms-hpt.txt`. A system whose `cms-hpt.txt` is missing shows `method: none` in `data\reports\hpt_catalog.csv`: find its price page in Chrome, put the URL in `hpt_txt_url` or `source_page_url`, rerun.

Proof the data is correct, for every hospital: `SHA256SUMS.txt` beside the raw file, `verify` 11 checks = 0 fail, row count in the manifest equals the DuckDB table, and the quality report.

## Settings the pipeline reads

`.env` at the repo root is read by every command (`manage.py` and `python -m pipeline.*` alike): `MESHKOR_RAW_DIR` (raw files, E:\), `MESHKOR_DATA_ROOT` (Parquet + DuckDB), `MESHKOR_SOURCES=sources_local.yaml`. If a run ever writes under `data\raw` on D:\, `.env` is missing or wrong; fix it and run `python tools\hpt_reset_yaml.py`.

## What happens when something fails (the ledger)

Every hospital × month has one row in `data\reports\hpt_ledger.xlsx` (and `.csv`): state, reason code, detail, attempts, next action. Open the Excel; red rows need a person. One hospital's failure never stops the run.

| Code | Meaning | Pipeline does | You do |
|---|---|---|---|
| NO_WEBSITE | no website in `hospital_sites.csv` | parks | add the website |
| NO_HPT_TXT | site has no `cms-hpt.txt` | retries once, parks | find the price page in Chrome, put its URL in `hpt_txt_url` / `source_page_url` |
| UNMATCHED | index lists locations, none matched this hospital's name | parks | put the exact location name in a `location_name` column for that CCN |
| AUTH | file behind a login (401/403 + login page) | parks | ask the hospital (contact in `hpt_catalog.csv`) or download by hand |
| BLOCKED | 403/429 bot wall, Chrome also refused | retries 3× | wait a day; if still blocked, by hand |
| NOT_FOUND | link 404 | retries once | check the page by hand |
| TIMEOUT / CONN | network | retries 3× | nothing; rerun later |
| HTML | server sent a web page instead of data | parks | open the link in Chrome and see what it asks |
| BAD_FORMAT / INVALID | not a CMS price file (header, columns, no codes, no prices) | parks, file kept on E:\ | tell the developer |
| PARSE_ERROR | loader failed on this file; file **quarantined**, others loaded | parks, release removed from yaml | tell the developer (error text is in the ledger) |
| VERIFY_FAIL | loaded but a check failed; Parquet moved to `data\ref\_quarantine\` | parks, removed from database | tell the developer |

Rerun = only what is open. `--retry-parked` tries parked hospitals again after you fixed something. A run ends with `data\reports\hpt_run_<date>.md`: counts per state and the "needs a person" table.

## If a hospital still fails (browser way, by hand)


1. Open the scoreboard: `python -m pipeline.hpt.progress`, read "Next actions" at the bottom. Pick the first hospital in the lowest tier.
2. In Chrome (VPN on): open `https://<website>/cms-hpt.txt`. If it is missing, open the hospital's site and search "price transparency" or "standard charges". Copy the page URL.
3. Click the price file link (`..._standardcharges.csv`, `.json` or `.zip`). Save to Downloads. Do not open or edit it.
4. Run one command from the repo root:
   ```powershell
   .\tools\hpt_one.ps1 -Ccn 360051 -Period 2026-11 -File "C:\Users\hansa\Downloads\310536568_miami-valley-hospital_standardcharges.csv" -Page "https://www.premierhealth.com/patients-and-visitors/billing/price-transparency"
   ```
   It does, in order, and stops at the first error:

   | Step | Command inside | What it does |
   |---|---|---|
   | 1 intake | `python -m pipeline.hpt.intake --write-yaml …` | Moves the file to `E:\…\MRF\2026-11\360051\` (never overwrites), unzips, hashes, writes `SHA256SUMS.txt`, logs to `hpt_downloads.csv`, adds the release to `config\sources_local.yaml`. If the file equals the previous month's, it says "unchanged" and stops: nothing to load. |
   | 2 load_ref | `python backend\manage.py load_ref ref_hospital_mrf` | Reads every registered file, writes Parquet per hospital × period. |
   | 3 build_duckdb | `python backend\manage.py build_duckdb` | Rebuilds the DuckDB tables and macros. |
   | 4 verify | `python -m pipeline.hpt.verify` | 11 checks per hospital. Must be 0 fail. |
   | 5 quality | `python -m pipeline.hpt.quality --ccn … --period …` | Quality report: payers, codes, multipliers, cash price, "Other" payers. |
   | 6 progress | `python -m pipeline.hpt.progress` | Rewrites the scoreboard. |

5. Read two things: the verify line (`N pass / 0 fail`) and the quality report `data\reports\hpt_quality_<ccn>_<period>.md`. Payers under "mapped to Other" → tell your friend; he adds a rule to `config\payer_groups.yaml` (no code).
6. Commit and push on branch `feature/hpt-data`: `config\sources_local.yaml`, `config\hospital_sites.csv`, `data\ref\_manifest\ref_hospital_mrf\*.json`, `data\reports\*.md`, `data\reports\*.csv`. Never the raw file, Parquet or DuckDB (`.gitignore` blocks them).

When the loader fails on a new hospital's file (a layout we have not seen), do not fix the file. Send your friend: the CCN, the error text, and the first 3 lines of the file (`Get-Content file.csv -TotalCount 3`). He changes the loader; you rerun step 4 of the script.

## Order of work (tiers in `config\hpt_tiers.csv`)

| Tier | Hospitals | Target |
|---|---|---|
| 1 | Miami Valley (360051), Cleveland Clinic main (360180), + any hospital on the pilot bills | this week |
| 2 | OhioHealth, Mount Carmel, Mercy Health, UC Health, Kettering, Summa, UH, MetroHealth, ProMedica, TriHealth, Christ, Nationwide Children's, Aultman | next 2–3 weeks |
| 3 | the rest of Ohio (`python -m pipeline.hpt.hospitals` prints them) | monthly job, over time |

First run `python -m pipeline.hpt.hospitals` once: it builds the full Ohio list (needs the DuckDB from Step 1) and prints hospitals with no website. Add websites to `config\hospital_sites.csv` as you find them. The scoreboard then counts all of Ohio, not just the 14 systems in the csv.

## Disk

| What | Where | Size |
|---|---|---|
| Raw files (never changed) | `E:\Hansavahini\Datasetof CMS\MRF\<period>\<ccn>\` (= `MESHKOR_RAW_DIR`) | 50 MB–2 GB each. Tier 1+2 ≈ 15 GB. All 90 ≈ 30–60 GB. Each later month adds only files that changed (same hash = not kept). |
| Parquet | `D:\Meshkor_Backend\meshkor-data\data\ref\ref_hospital_mrf\` | ≈ 10 % of raw. All 90 ≈ 3–6 GB. |
| DuckDB | `data\meshkor.duckdb` | grows about the same as Parquet, ≈ +4 GB at 90. |
| History (Wayback) | `MRF\<2024-mm>\<ccn>\` | pilot hospitals only, ≈ 5 GB. |
| Work copies | `data\work\` | temporary, up to the largest file (2 GB); delete any time. |

Plan: **60 GB free on E:\** for raw, **12 GB free on D:\** for Parquet + DuckDB. If D:\ is short, move only the raw folder, never the repo: raw is already on E:\. To move Parquet and DuckDB too, set `MESHKOR_DATA_ROOT=F:\meshkor-data` in `.env`, copy the existing `data\` folder there, and keep `data\ref\_manifest` and `data\reports` committed from that path (the commands read `MESHKOR_DATA_ROOT`, Git does not care where it is).

## Monthly (from month 2)

1st of each month, or Task Scheduler: `python -m pipeline.hpt.download --period <yyyy-mm>` for hospitals Python can reach; browser + `hpt_one.ps1` for the blocked ones. Unchanged files are detected by hash and not kept. A changed file becomes a new release; your friend sets `effective_end` of the old release to the day before the new `last_updated_on` (one yaml line).
