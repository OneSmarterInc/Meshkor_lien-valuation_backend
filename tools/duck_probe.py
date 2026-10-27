r"""Show the FULL DuckDB error for a price CSV, and the raw text around the line it names.
The load log keeps only the first line of the error; this prints all of it.

  python tools\duck_probe.py "E:\Hansavahini\Datasetof CMS\MRF\2026-10\360039\311480941_Genesis-Healthcare-System_standardcharges.csv"

It reads the file with the same options the loader uses. It changes nothing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402

from pipeline.ref import hospital_mrf as H  # noqa: E402


def show_lines(path: Path, n: int, radius: int = 2) -> None:
    print(f"\nraw text around line {n} (line numbers as DuckDB counts them):")
    with open(path, "rb") as f:
        for i, line in enumerate(f, 1):
            if n - radius <= i <= n + radius:
                q = line.count(b'"')
                odd = "  <-- odd number of quotes" if q % 2 else ""
                high = sum(1 for b in line if b > 127)
                print(f"  {i}: {len(line)} bytes, {q} quotes, {high} non-ASCII bytes{odd}")
                print("     " + repr(line[:300]))
            if i > n + radius:
                break


READ = """SELECT count(*) FROM read_csv('{p}', skip={skip}, header=true, all_varchar=true,
          quote='"', escape='"', delim=',', strict_mode=false, encoding='utf-8')"""


class _Quiet:
    def warn(self, *_a, **_k) -> None:
        print("  " + str(_a[0]))


def try_read(path: Path, skip: int):
    con = duckdb.connect()
    try:
        n = con.execute(READ.format(p=path.as_posix(), skip=skip)).fetchall()[0][0]
        return n, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    meta, header, skip = H.read_prefix(path)
    print(f"header row found, {len(header)} columns, skip={skip} lines")
    n, err = try_read(path, skip)
    if err is None:
        print(f"DuckDB read the whole file: {n:,} rows. No error.")
        return 0
    print("\nFIRST ERROR (original file):\n" + err[:1500])
    m = re.search(r"Line:?\s*(\d+)", err)
    if m:
        show_lines(path, int(m.group(1)))
    if "not utf-8" in err or "Invalid unicode" in err:
        import tempfile
        print("\nThe loader now makes a UTF-8 copy (Windows-1252 bytes decoded) and reads that. Doing the same here...")
        with tempfile.TemporaryDirectory() as t:
            clean = H.utf8_clean_copy(path, Path(t), _Quiet())
            n, err2 = try_read(clean, skip)
            if err2 is None:
                print(f"The UTF-8 copy reads fine: {n:,} rows.")
                return 0
            print("\nSECOND ERROR (UTF-8 copy):\n" + err2[:1500])
            m = re.search(r"Line:?\s*(\d+)", err2)
            if m:
                show_lines(clean, int(m.group(1)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
