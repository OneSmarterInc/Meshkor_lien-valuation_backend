r"""Find the rows of a price CSV whose number of fields differs from the header.

Use it when load_ref says  CSV Error on Line: N  for a hospital. Prints the header row, and the first
rows (with their line numbers) that have too many or too few fields. Nothing is changed.

  python tools\csv_probe.py "E:\Hansavahini\Datasetof CMS\MRF\2026-10\360039\<file>.csv"
"""
import csv
import sys

csv.field_size_limit(1 << 30)


def main(path: str, show: int = 5) -> int:
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        r = csv.reader(f)
        head, head_line, n = None, 0, 0   # n = records after the header
        bad = []
        for row in r:
            if head is None:
                if any(c.strip().lower() == "description" for c in row):
                    head, head_line = row, r.line_num
                    print(f"header found at line {head_line}: {len(head)} fields")
                    print("  " + " | ".join(head[:12]) + (" | ..." if len(head) > 12 else ""))
                continue
            n += 1
            if len(row) != len(head):
                bad.append((r.line_num, len(row), row))
        print(f"records after header: {n}; records with a different field count: {len(bad)}")
        for line, cnt, row in bad[:show]:
            print(f"\nline {line}: {cnt} fields (header has {len(head)})")
            print("  " + " | ".join(c[:40] for c in row[:14]))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
