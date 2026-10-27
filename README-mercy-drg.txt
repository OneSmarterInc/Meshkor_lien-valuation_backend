Mercy "DRG" fix + load_ref --ccn

pipeline/ref/hospital_mrf.py     bare code type DRG: severity word at end of description (MINOR/MODERATE/MAJOR/EXTREME)
                                 -> apr_drg; otherwise -> code_other. TRIS-DRG -> code_other. Warning line counts both.
pipeline/runner.py               MESHKOR_ONLY_CCN filter (load only the named hospitals)
backend/.../commands/load_ref.py new option  --ccn 360016,360064  (repeatable or comma list)
tools/csv_probe.py               shows rows whose field count differs from the header (for CSV Error on Line N)
tests/test_hpt_pipeline.py       2 new tests (bare DRG mapping, --ccn filter)

Unzip over the repo root (same folders). Then:
  python backend\manage.py load_ref ref_hospital_mrf --period 2026-10 --ccn 360001,360016,360056,360064,360066,360086,360089,360112,360161,360172,360234,360236,360262,360276,360374,361306,361310,361312,361328
  python backend\manage.py build_duckdb --only ref_hospital_mrf
  python -m pipeline.hpt.verify --period 2026-10 --quarantine
