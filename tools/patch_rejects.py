r"""Third fallback for the CSV read: when plain AND null_padding reads fail, read with
ignore_errors + store_rejects. Bad rows are skipped and counted; the release is quarantined only
if more than 0.5% of rows are bad. Run once after tools\patch_makeraw.py. Safe to run twice.
  python tools\patch_rejects.py
"""
import re, sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "pipeline/ref/hospital_mrf.py")
s = p.read_text(encoding="utf-8-sig")
if "store_rejects" in s:
    print("already patched"); sys.exit(0)
new = '''    def make_raw(path: Path, pad: bool = False, ign: bool = False) -> None:
        con.execute("DROP VIEW IF EXISTS _raw")
        opt = ("null_padding=true, " if pad else "") + ("ignore_errors=true, store_rejects=true, " if ign else "")
        con.execute(f"""CREATE VIEW _raw AS SELECT * FROM read_csv('{path.as_posix()}', skip={skip},
                        header=true, all_varchar=true, quote='"', escape='"', delim=',',
                        strict_mode=false, {opt}encoding='utf-8')""")
        n = con.execute("SELECT count(*) FROM _raw").fetchall()[0][0]      # forces a full read now
        if ign:
            bad = con.execute("SELECT count(*) FROM reject_errors").fetchall()[0][0]
            ctx.warn(f"{m.name}: {bad} malformed CSV rows skipped out of {n + bad}")
            if bad > max(10, 0.005 * (n + bad)):
                raise ValueError(f"too many malformed CSV rows: {bad} of {n + bad}")

    def read_any(path: Path, pad: bool, ign: bool = False) -> None:
        try:
            make_raw(path, pad, ign)
        except duckdb.InvalidInputException as e:
            if "not utf-8" not in str(e) and "Invalid unicode" not in str(e):
                raise
            make_raw(utf8_clean_copy(path, work, ctx), pad, ign)

    try:
        read_any(src, False)
    except duckdb.Error:
        ctx.warn(f"{m.name}: plain CSV read failed; retried with null_padding (short rows padded)")
        try:
            read_any(src, True)
        except duckdb.Error:
            ctx.warn(f"{m.name}: null_padding read failed; retried skipping malformed rows")
            read_any(src, True, True)
'''
pat = re.compile(r"    def make_raw\(path: Path.*?        read_any\(src, True\)\n", re.S)
s2, n = pat.subn(lambda _m: new, s, count=1)
if n != 1:
    print("block not found: run tools\\patch_makeraw.py first"); sys.exit(1)
p.write_text(s2, encoding="utf-8")
print("patched", p)