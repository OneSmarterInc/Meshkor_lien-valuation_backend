"""Step 2 (hospital price transparency files): hospital list, file discovery, download,
archive search and quality reports. The loader itself is pipeline/ref/hospital_mrf.py.

    python -m pipeline.hpt.hospitals            -> data/ref/hpt_hospitals.parquet (+ csv)
    python -m pipeline.hpt.discover             -> data/ref/hpt_catalog.parquet  (+ csv)
    python -m pipeline.hpt.download --period 2026-11 [--only 360051,360180]
    python -m pipeline.hpt.archive  --ccn 360085
    python -m pipeline.hpt.quality  --ccn 360085 --period 2026-10
    python -m pipeline.hpt.verify   [--ccn 360085]
"""
