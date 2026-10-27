MeshKor: fix for the 4 rejected hospital files (Knox, Holzer, Blanchard Valley, Western Reserve)
+ a probe tool for Genesis

WHAT WAS WRONG (found with tools\check_rejected.py)
  360040 Knox             JSON lacks 'standard_charge_information' near the top
                          -> the check read only the first 200 KB. Knox has a long modifier list before the charges.
  360054 Holzer           File is not latin-1 encoded
                          -> the check used latin-1 for a file with Windows-1252 bytes. The loader already used the
                             right fix (UTF-8 copy). The check now uses the same fix.
  360095 Blanchard Valley missing columns code|1, standard_charge|gross
  360150 Western Reserve  -> these headers are written "code | 1" (spaces around the bar). Header names are now
                             read without those spaces, in the check and in the loader.
  360039 Genesis          CSV Error on Line 3328 (cause not known yet; use tools\duck_probe.py)

WHAT CHANGED (4 files + 1 new)
  pipeline/ref/hospital_mrf.py   norm(): spaces around "|" are ignored. (Contains the Mercy DRG fix too.)
  pipeline/hpt/validate.py       streams the JSON top-level keys; cp1252 clean copy; header names via norm().
  tools/duck_probe.py            NEW. Prints the FULL DuckDB error for a CSV and the raw text around the bad line.
  tests/test_hpt_pipeline.py     3 new tests (spaced header + full load, mixed encoding, long modifier list).
  Tests: 21 passed (tests/test_hpt_pipeline.py + tests/test_hpt.py).

HOW TO APPLY (from D:\Meshkor_Backend\meshkor-data, .venv on)
  1. Extract the zip over the project folder. Say yes to replace.
  2. python -m pytest tests\test_hpt_pipeline.py -q            (all pass)
  3. $env:PYTHONPATH=(Get-Location).Path
     python tools\check_rejected.py 360040 360054 360095 360150   (each line must say OK)
  4. Register the 4 files that are already in the raw folder (no new download, no move):
     python -m pipeline.hpt.intake --period 2026-10 --ccn 360040 --page "member6 re-download, same file" --write-yaml
     python -m pipeline.hpt.intake --period 2026-10 --ccn 360054 --page "member6 re-download, same file" --write-yaml
     python -m pipeline.hpt.intake --period 2026-10 --ccn 360095 --page "member6 re-download, same file" --write-yaml
     python -m pipeline.hpt.intake --period 2026-10 --ccn 360150 --page "member6 re-download, same file" --write-yaml
  5. python backend\manage.py load_ref ref_hospital_mrf --period 2026-10 --ccn 360040,360054,360095,360150
  6. python backend\manage.py build_duckdb
     python -m pipeline.hpt.verify --period 2026-10 --quarantine
     python -m pipeline.hpt.progress

GENESIS
  python tools\duck_probe.py "E:\Hansavahini\Datasetof CMS\MRF\2026-10\360039\311480941_Genesis-Healthcare-System_standardcharges.csv"
  Send the whole output. It writes a UTF-8 copy in your temp folder (about 1 GB) and deletes it at the end.

NOTE
  Knox: the check now passes the top of the file. The full JSON load is not tested on the real file. If it fails, send the error.
