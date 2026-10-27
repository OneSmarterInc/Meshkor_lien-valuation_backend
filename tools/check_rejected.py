import sys, tempfile
from pathlib import Path
from pipeline.hpt.validate import validate
raw = Path(r"E:\Hansavahini\Datasetof CMS\MRF\2026-10")
for ccn in sys.argv[1:]:
    files = [p for p in (raw / ccn).iterdir() if p.suffix.lower() in (".csv", ".json")]
    f = max(files, key=lambda p: p.stat().st_size)
    with tempfile.TemporaryDirectory() as t:
        ok, code, detail, info = validate(f, Path(t))
    print(ccn, "OK" if ok else "FAIL", code, detail)
