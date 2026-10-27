"""Pre-load validation of a downloaded price file: cheap checks BEFORE the file is registered
and the heavy load runs. Returns (ok, code, detail, info).

Checks: real data file (not HTML), CMS header found (hospital_name, last_updated_on, version),
a layout we know (tall / wide / JSON), the required columns present, the first rows parse,
at least one code column, at least one rate column. The first 2,000 rows are parsed with the
same SQL the loader uses, so a parse error is caught here, not in load_ref.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import duckdb

from ..ref import hospital_mrf as H

REQUIRED_TALL = ["description", "code|1", "standard_charge|gross"]
REQUIRED_WIDE = ["description", "code|1"]


def _data_file(path: Path) -> Path:
    if path.suffix.lower() == ".zip" and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
        inner = [path.parent / n for n in names if (path.parent / n).exists()]
        if inner:
            return max(inner, key=lambda p: p.stat().st_size)
    return path


def validate(path: Path, work: Path) -> tuple[bool, str, str, dict]:
    path = _data_file(Path(path))
    info: dict = {"file": path.name, "bytes": path.stat().st_size}
    with open(path, "rb") as f:
        head = f.read(2048)
    t = head.lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if t[:1] == b"<" or b"<html" in t or b"<!doctype" in t:
        return False, "HTML", "web page, not a data file", info
    if path.stat().st_size < 1000:
        return False, "BAD_FORMAT", f"file is only {path.stat().st_size} bytes", info
    work.mkdir(parents=True, exist_ok=True)
    try:
        if path.suffix.lower() == ".json":
            path = H.json_clean_copy(path, work)          # BOM / UTF-16 / leading junk, same as the loader
            # the top-level keys, streamed up to the big array (a file can hold a long modifier list before it)
            keys = _json_top_keys(path)
            for key in ("hospital_name", "last_updated_on", "standard_charge_information"):
                if key not in keys:
                    return False, "INVALID", f"JSON lacks '{key}' at the top level", info
            info["layout"] = "json"
            # parse the first records exactly as the loader will, on a truncated copy
            sample = work / (path.stem + ".sample.json")
            _json_head(path, sample)
            csv_path, meta = H.json_to_tall_csv(sample, work)
            meta_, header, skip = H.read_prefix(csv_path)
            layout = "json"
        else:
            meta, header, skip = H.read_prefix(path)
            layout = H.layout_of(header)
            info["layout"] = layout
            csv_path = path
        info.update(hospital_name=meta.get("hospital_name", ""), last_updated_on=meta.get("last_updated_on", ""),
                    version=meta.get("version", ""), columns=len(header))
        if not meta.get("hospital_name"):
            return False, "INVALID", "no hospital_name in the first rows (not a CMS template?)", info
        if layout not in ("tall", "wide", "json"):
            return False, "INVALID", f"layout not recognised ({layout}); header starts {header[:6]}", info
        low = [H.norm(h) for h in header]
        req = REQUIRED_TALL if layout in ("tall", "json") else REQUIRED_WIDE
        miss = [c for c in req if c not in low]
        if miss:
            return False, "INVALID", f"missing columns {miss}; header starts {header[:8]}", info
        con = duckdb.connect()
        src = csv_path
        try:
            con.execute(f"""CREATE VIEW _raw AS SELECT * FROM (SELECT * FROM read_csv('{src.as_posix()}', skip={skip}, header=true,
                            all_varchar=true, quote='"', escape='"', delim=',', strict_mode=false, encoding='utf-8') LIMIT 2000)""")
            con.execute("SELECT count(*) FROM _raw").fetchall()
        except duckdb.InvalidInputException as e:
            if "not utf-8" in str(e) or "Invalid unicode" in str(e):
                con.execute("DROP VIEW IF EXISTS _raw")
                clean = H.utf8_clean_copy(src, work, _Quiet())          # same fix the loader applies
                con.execute(f"""CREATE VIEW _raw AS SELECT * FROM (SELECT * FROM read_csv('{clean.as_posix()}', skip={skip}, header=true,
                                all_varchar=true, quote='"', escape='"', delim=',', strict_mode=false, encoding='utf-8') LIMIT 2000)""")
                con.execute("SELECT count(*) FROM _raw").fetchall()
            else:
                return False, "PARSE_ERROR", str(e).splitlines()[0][:200], info
        inner = f"SELECT {H._tall_select(header)} FROM _raw" if layout in ("tall", "json") else H._wide_select(header)
        n = con.execute(f"SELECT count(*) FROM ({inner})").fetchall()[0][0]
        codes = con.execute(f"SELECT count(*) FROM ({inner}) WHERE code_1 IS NOT NULL OR code_2 IS NOT NULL").fetchall()[0][0]
        rates = con.execute(f"""SELECT count(*) FROM ({inner}) WHERE gross_charge IS NOT NULL OR negotiated_dollar IS NOT NULL
                                OR negotiated_percentage IS NOT NULL OR negotiated_algorithm IS NOT NULL OR discounted_cash IS NOT NULL""").fetchall()[0][0]
        con.close()
        info.update(sample_rows=n, sample_with_code=codes, sample_with_rate=rates)
        if n == 0:
            return False, "INVALID", "first 2,000 rows produce 0 rows", info
        if codes == 0:
            return False, "INVALID", "no row in the sample has a code", info
        if rates == 0:
            return False, "INVALID", "no row in the sample has any price", info
        return True, "", f"{layout}, {n} sample rows, hospital {meta.get('hospital_name')!r}, dated {meta.get('last_updated_on')}", info
    except ValueError as e:
        if "layout" in str(e) or "header" in str(e).lower():
            return False, "INVALID", str(e).splitlines()[0][:200], info
        return False, "PARSE_ERROR", f"ValueError: {str(e).splitlines()[0][:200]}", info
    except Exception as e:  # noqa: BLE001
        return False, "PARSE_ERROR", f"{type(e).__name__}: {str(e).splitlines()[0][:200]}", info


class _Quiet:
    def warn(self, *_a, **_k) -> None:
        pass


def _json_top_keys(path: Path) -> set:
    """Top-level keys seen before standard_charge_information (stops there; the array can be huge)."""
    import ijson
    keys: set = set()
    with open(path, "rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix == "" and event == "map_key":
                keys.add(value)
                if value == "standard_charge_information":
                    break
    return keys


def _json_head(src: Path, dest: Path, n_items: int = 300) -> None:
    """Copy the header fields the loader reads and the first n items of standard_charge_information."""
    import ijson
    out: dict = {}
    with open(src, "rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix.startswith("standard_charge_information") or (prefix == "" and event == "map_key" and value == "standard_charge_information"):
                break
            if prefix in ("hospital_name", "last_updated_on", "version") and event in ("string", "number"):
                out[prefix] = value if event == "string" else str(value)
            elif prefix in ("hospital_location.item", "hospital_address.item") and event == "string":
                out.setdefault(prefix.split(".")[0], []).append(value)
            elif prefix == "license_information.license_number" and event == "string":
                out["license_information"] = {"license_number": value}
            elif prefix == "affirmation.confirm_affirmation" and event == "boolean":
                out["affirmation"] = {"confirm_affirmation": value}
    items = []
    with open(src, "rb") as f:
        for it in ijson.items(f, "standard_charge_information.item"):
            items.append(it)
            if len(items) >= n_items:
                break
    out["standard_charge_information"] = items
    dest.write_text(json.dumps(out, default=str), encoding="utf-8")
