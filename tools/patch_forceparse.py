r"""Loader: parse EVERY column once inside the try block, so a non-UTF-8 byte deep in the file
(Genesis, line 3328 and later) is caught there and the UTF-8 copy is used. count(*) alone skips text.
  python tools\patch_forceparse.py
Run after patch_makeraw.py and patch_rejects.py. Safe to run twice.
"""
import re, sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "pipeline/ref/hospital_mrf.py")
s = p.read_text(encoding="utf-8-sig")
if "max(length(COLUMNS(*)))" in s:
    print("already patched"); sys.exit(0)
pat = re.compile(r'^( +)((?:n = )?con\.execute\("SELECT count\(\*\) FROM _raw"\)\.fetchall\(\))', re.M)
m = pat.search(s)
if not m:
    print("line not found; send me the lines around 'def make_raw'"); sys.exit(1)
i = m.group(1)
ins = (f'{i}try:\n{i}    con.execute("SELECT max(length(COLUMNS(*))) FROM _raw").fetchall()   # parses every column\n'
       f'{i}except duckdb.OutOfMemoryException:\n{i}    pass\n')
p.write_text(s[:m.start()] + ins + s[m.start():], encoding="utf-8")
print("patched", p)