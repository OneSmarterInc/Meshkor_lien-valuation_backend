r"""Make the CSV read retry with null_padding ONLY when the plain read fails (fixes Adams County
without breaking Select Specialty). Also sets memory 8GB / threads 2. Safe to run twice.
  python tools\patch_makeraw.py
"""
import re, sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "pipeline/ref/hospital_mrf.py")
s = p.read_text(encoding="utf-8-sig")
if "read_any(src, True)" in s:
    print("already patched"); sys.exit(0)
new = '''    def make_raw(path: Path, pad: bool = False) -> None:
        con.execute("DROP VIEW IF EXISTS _raw")
        padopt = "null_padding=true, " if pad else ""
        con.execute(f"""CREATE VIEW _raw AS SELECT * FROM read_csv('{path.as_posix()}', skip={skip},
                        header=true, all_varchar=true, quote='"', escape='"', delim=',',
                        strict_mode=false, {padopt}encoding='utf-8')""")
        con.execute("SELECT count(*) FROM _raw").fetchall()      # forces a full read now

    def read_any(path: Path, pad: bool) -> None:
        try:
            make_raw(path, pad)
        except duckdb.InvalidInputException as e:
            if "not utf-8" not in str(e) and "Invalid unicode" not in str(e):
                raise
            make_raw(utf8_clean_copy(path, work, ctx), pad)

    try:
        read_any(src, False)
    except duckdb.Error:
        ctx.warn(f"{m.name}: plain CSV read failed; retried with null_padding (short rows padded)")
        read_any(src, True)
'''
pat = re.compile(r"    def make_raw\(path: Path\).*?make_raw\(utf8_clean_copy\(src, work, ctx\)\)\n", re.S)
s2, n = pat.subn(lambda _m: new, s, count=1)
if n != 1:
    print("make_raw block not found; send me lines around 'def make_raw'"); sys.exit(1)
s2 = s2.replace("SET memory_limit='2GB'", "SET memory_limit='8GB'")
if "SET threads=2" not in s2:
    s2 = s2.replace("""con.execute("SET memory_limit='8GB'")""", """con.execute("SET memory_limit='8GB'")\n    con.execute("SET threads=2")""")
p.write_text(s2, encoding="utf-8")
print("patched", p)