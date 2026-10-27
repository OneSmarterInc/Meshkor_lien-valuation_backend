from pathlib import Path
import duckdb

DATA_ROOT = Path("data")  # Adjust this path based on your environment


def main():
    # Accept only the expected numeric identifiers to avoid accidental paths.
    if not ccn.isdigit() or len(ccn) != 6:
        print(f"Invalid CCN: {ccn!r}. Expected a 6-digit CCN.")
        return 2

    if not code.isdigit():
        print(f"Invalid code: {code!r}. Expected a numeric HCPCS or MS-DRG code.")
        return 2

    parquet_path = DATA_ROOT / f"{ccn}_2026-10" / "part-000.parquet"

    if not parquet_path.is_file():
        print(f"PARQUET FILE NOT FOUND: {parquet_path}")
        print("Check the folder name and ask the lead before changing any data.")
        return 1

    query = """
    SELECT
        hospital_name,
        hcpcs,
        ms_drg,
        payer_name,
        gross_charge,
        negotiated_dollar
    FROM read_parquet(?)
    WHERE CAST(hcpcs AS VARCHAR) = ?
       OR CAST(ms_drg AS VARCHAR) = ?
    LIMIT 8
    """

    try:
        con = duckdb.connect(database=":memory:", read_only=False)
        rows = con.execute(query, [str(parquet_path), code, code]).fetchall()
        columns = [description[0] for description in con.description]
        con.close()
    except Exception as exc:
        print(f"QUERY ERROR: {exc}")
        return 1

    print(f"CCN: {ccn}")
    print(f"Code searched: {code}")
    print(f"Parquet file: {parquet_path}")
    print(f"Rows found: {len(rows)}")

    if not rows:
        print("NO ROWS for this code.")
        return 0

    # Plain-text output is easy to copy into the comparison notes.
    print()
    print(" | ".join(columns))
    print("-" * 120)
    for row in rows:
        print(" | ".join("" if value is None else str(value) for value in row))

    return 0


if __name__ == "__main__":
    # Note: Ensure `ccn` and `code` variables are defined or passed in your script execution flow.
    raise SystemExit(main())