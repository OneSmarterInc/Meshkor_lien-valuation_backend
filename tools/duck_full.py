r"""Like duck_probe.py, but parses EVERY column (count(*) alone does not). Streams the file, so it
needs little memory. Prints the full error and the raw text around the failing line.

  python tools\duck_full.py "E:\Hansavahini\Datasetof CMS\MRF\2026-10\360039\311480941_Genesis-Healthcare-System_standardcharges.csv"
"""
import re, sys
from pathlib import Path

import duckdb
import duck_probe as P
from pipeline.ref import hospital_mrf as H

path = Path(sys.argv[1])
meta, header, skip = H.read_prefix(path)
print(f"header row found, {len(header)} columns, skip={skip} lines")
con = duckdb.connect()
q = f"""SELECT * FROM read_csv('{path.as_posix()}', skip={skip}, header=true, all_varchar=true,
        quote='"', escape='"', delim=',', strict_mode=false, encoding='utf-8')"""
try:
    res = con.execute(q); n = 0
    while True:
        rows = res.fetchmany(100000)
        if not rows: break
        n += len(rows)
    print(f"all columns parsed, {n:,} rows, no error")
except Exception as e:  # noqa: BLE001
    err = str(e)
    print("\nERROR:\n" + err[:2500])
    m = re.search(r"Line:?\s*(\d+)", err)
    if m: P.show_lines(path, int(m.group(1)), 3)