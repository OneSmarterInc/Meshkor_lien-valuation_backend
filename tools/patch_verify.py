r"""verify.py: when the plain row count of the raw CSV fails, count again with null_padding
(same fallback the loader uses). Fixes 'raw csv readable' FAIL for Adams County.
  python tools\patch_verify.py
"""
import re, sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "pipeline/hpt/verify.py")
s = p.read_text(encoding="utf-8-sig")
if "_cnt(\", null_padding=true\")" in s:
    print("already patched"); sys.exit(0)
pat = re.compile(r"( +)n_raw = con\.execute\(f\"\"\"SELECT count\(\*\) FROM read_csv\('\{read_path\.as_posix\(\)\}', skip=\{skip\}, header=true,\s*"
                 r"all_varchar=true, quote='\"', escape='\"', delim=',', strict_mode=false\)\"\"\"\)\.fetchone\(\)\[0\]\n")
def rep(m):
    i = m.group(1)
    return (f"{i}def _cnt(extra=\"\"):\n"
            f"{i}    return con.execute(f\"\"\"SELECT count(*) FROM read_csv('{{read_path.as_posix()}}', skip={{skip}}, header=true,\n"
            f"{i}        all_varchar=true, quote='\"', escape='\"', delim=',', strict_mode=false{{extra}})\"\"\").fetchone()[0]\n"
            f"{i}try:\n{i}    n_raw = _cnt()\n{i}except duckdb.Error:\n{i}    n_raw = _cnt(\", null_padding=true\")\n")
s2, n = pat.subn(rep, s, count=1)
if n != 1:
    print("block not found; send me the 'n_raw =' lines of pipeline\\hpt\\verify.py"); sys.exit(1)
p.write_text(s2, encoding="utf-8"); print("patched", p)