"""Step 2 — ref_hospital_mrf: hospital price transparency files (45 CFR 180 machine-readable files).

One release = one hospital (CCN) × one download period. The release in
config/sources_local.yaml looks like:

    ref_hospital_mrf:
      loader: hospital_mrf
      releases:
      - period: "2026-10"
        ccn: "360085"
        effective_start: 2026-07-01        # the file's last_updated_on (or the download month)
        effective_end: 9999-12-31          # set to the day before the next file once it is loaded
        page: https://wexnermedical.osu.edu/patient-and-visitor-guide/patient-pricing-lists
        file: MRF/2026-10/360085
        members:
          mrf: "*standardcharges*.csv"     # or *.json

Three CMS template layouts are read into the same columns (the guide's `hpt_rates`):
  * CSV "tall"  (one row per code × payer × plan)                    v2.x and v3.x
  * CSV "wide"  (one row per code, one column family per payer|plan)  v2.x and v3.x
  * JSON        (standard_charge_information[] → standard_charges[] → payers_information[])
JSON is streamed with ijson into a tall CSV in data/work, then read like a tall CSV.

Every row carries the hospital block (ccn, hospital_name, ein, type2_npis, mrf_version,
last_updated_on), the derived join keys (hcpcs, ms_drg, apr_drg, rc, ndc, cdm), a cleaned
payer_group (config/payer_groups.yaml) and the lineage columns.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb
import polars as pl

from ..common import config
from ..common.lineage import LINEAGE_COLS, as_date
from ..runner import Context, ReleaseOutput

# Not STREAM: load_release writes each part with DuckDB (memory stays flat) and hands the
# runner a MrfPart; finalize/write (below) move the parts into data/ref/ref_hospital_mrf/.

# CMS tall header -> our column.  Unknown headers stop the load (the hospital used a
# column outside the template; add it here on purpose).
COLMAP = {
    "description": "description",
    "code|1": "code_1", "code|1|type": "code_1_type",
    "code|2": "code_2", "code|2|type": "code_2_type",
    "code|3": "code_3", "code|3|type": "code_3_type",
    "code|4": "code_4", "code|4|type": "code_4_type",
    "modifiers": "modifiers",
    "setting": "setting",
    "billing_class": "billing_class",
    "drug_unit_of_measurement": "drug_unit",
    "drug_type_of_measurement": "drug_type",
    "standard_charge|gross": "gross_charge",
    "standard_charge|discounted_cash": "discounted_cash",
    "payer_name": "payer_name",
    "plan_name": "plan_name",
    "standard_charge|negotiated_dollar": "negotiated_dollar",
    "standard_charge|negotiated_percentage": "negotiated_percentage",
    "standard_charge|negotiated_algorithm": "negotiated_algorithm",
    "estimated_amount": "estimated_amount",
    "median_amount": "median_amount",
    "10th_percentile": "pct_10",
    "90th_percentile": "pct_90",
    "count": "rate_count",
    "standard_charge|methodology": "methodology",
    "standard_charge|min": "charge_min",
    "standard_charge|max": "charge_max",
    "additional_payer_notes": "payer_notes",
    "additional_generic_notes": "notes",
}
MONEY = {"gross_charge", "discounted_cash", "negotiated_dollar", "negotiated_percentage",
         "estimated_amount", "median_amount", "pct_10", "pct_90", "charge_min", "charge_max"}
INTS = {"rate_count"}
# wide layout: metric names that appear as "<metric>|payer|plan" (3 parts)
WIDE_3 = {"estimated_amount": "estimated_amount", "additional_payer_notes": "payer_notes",
          "median_amount": "median_amount", "10th_percentile": "pct_10", "90th_percentile": "pct_90",
          "count": "rate_count"}
# wide layout: "standard_charge|payer|plan|<metric>" (4 parts)
WIDE_4 = {"negotiated_dollar": "negotiated_dollar", "negotiated_percentage": "negotiated_percentage",
          "negotiated_algorithm": "negotiated_algorithm", "methodology": "methodology"}
CODE_TYPES = {  # derived join column -> code types that feed it
    "hcpcs": ("HCPCS", "CPT"), "ms_drg": ("MS-DRG",), "apr_drg": ("APR-DRG",), "rc": ("RC",),
    "ndc": ("NDC",), "cdm": ("CDM", "LOCAL"),
}

_payer_rules: list[tuple[re.Pattern, str]] | None = None


def payer_group_rules() -> list[tuple[re.Pattern, str]]:
    global _payer_rules
    if _payer_rules is None:
        rules = config.load_yaml("payer_groups.yaml")["groups"]
        _payer_rules = [(re.compile(r["match"], re.I), r["group"]) for r in rules]
    return _payer_rules


_extra_rules: list[tuple[re.Pattern, str]] = []


def set_extra_payer_names(pairs) -> None:
    """Names added by a MeshKor admin (the portal's Payer names page): (name, group). Each name is matched
    as a whole phrase in any case, and is tried before config/payer_groups.yaml."""
    global _extra_rules
    _extra_rules = [(re.compile(r"(?<!\w)" + re.escape(" ".join(n.split())).replace(r"\ ", r"\s+") + r"(?!\w)", re.I), g)
                    for n, g in pairs if n and n.strip() and g]


def payer_groups() -> list[str]:
    """Every group named in config/payer_groups.yaml, in file order."""
    out = []
    for _rx, g in payer_group_rules():
        if g not in out:
            out.append(g)
    return out


def payer_group(payer: str | None, plan: str | None) -> str:
    text = f"{payer or ''} {plan or ''}"
    for rx, grp in _extra_rules:
        if rx.search(text):
            return grp
    for rx, grp in payer_group_rules():
        if rx.search(text):
            return grp
    return "Other"


# ----------------------------------------------------------------------------- header block

def read_prefix(path: Path):
    """Rows 1-2 = hospital block, row 3 = column header. A quoted field may hold a newline,
    so a record ends where the quote count is even. Returns (meta, header, lines_to_skip)."""
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        text = f.read(400_000)
    rows, lines_per_row, buf, n = [], [], "", 0
    for line in io.StringIO(text):
        buf += line; n += 1
        if buf.count('"') % 2 == 0:
            rows.append(next(csv.reader(io.StringIO(buf))))
            lines_per_row.append(n); buf, n = "", 0
            if len(rows) == 3:
                break
    if len(rows) < 3:
        raise ValueError(f"{path.name}: could not find the 3 header rows of the CMS template")
    meta = {k.strip(): v for k, v in zip(rows[0], rows[1])}
    header = [c.strip() for c in rows[2]]
    return meta, header, lines_per_row[0] + lines_per_row[1]


def utf8_clean_copy(src: Path, work: Path, ctx: Context) -> Path:
    """Some hospitals leave Windows-1252 bytes in descriptions. Write a UTF-8 copy in
    data/work (the raw file is never touched) and say how many lines needed it."""
    clean = work / (src.stem + ".utf8.csv")
    bad = 0
    with open(src, "rb") as fi, open(clean, "w", encoding="utf-8", newline="") as fo:
        for line in fi:
            try:
                fo.write(line.decode("utf-8"))
            except UnicodeDecodeError:
                bad += 1
                fo.write(line.decode("cp1252", errors="replace"))
    ctx.warn(f"{src.name}: {bad} lines were not UTF-8; decoded as cp1252 (descriptions only)")
    return clean


def layout_of(header: list[str]) -> str:
    if "payer_name" in header:
        return "tall"
    if any(h.startswith("standard_charge|") and h.count("|") == 3 for h in header):
        return "wide"
    raise ValueError(f"unknown CSV layout; header starts {header[:8]}")


# ----------------------------------------------------------------------------- JSON -> tall CSV

def json_to_tall_csv(src: Path, work: Path) -> tuple[Path, dict]:
    """Stream a CMS JSON file (v2.x/v3.x) into a tall CSV with the same header the CSV
    template uses, so one reader serves both. Returns (csv_path, hospital_meta)."""
    import ijson
    out = work / (src.stem + ".tall.csv")
    meta: dict = {}
    hdr = ["description", "code|1", "code|1|type", "code|2", "code|2|type", "code|3", "code|3|type",
           "code|4", "code|4|type", "modifiers", "setting", "billing_class",
           "drug_unit_of_measurement", "drug_type_of_measurement",
           "standard_charge|gross", "standard_charge|discounted_cash", "payer_name", "plan_name",
           "standard_charge|negotiated_dollar", "standard_charge|negotiated_percentage",
           "standard_charge|negotiated_algorithm", "estimated_amount", "median_amount",
           "10th_percentile", "90th_percentile", "count", "standard_charge|methodology",
           "standard_charge|min", "standard_charge|max", "additional_payer_notes",
           "additional_generic_notes"]
    # top-level scalars first (cheap: they precede the big array in every file we have seen)
    with open(src, "rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix in ("hospital_name", "last_updated_on", "version") and event in ("string", "number"):
                meta[prefix] = str(value)
            elif prefix == "hospital_location.item" and event == "string":
                meta["location_name"] = (meta.get("location_name", "") + "|" + value).strip("|")
            elif prefix == "hospital_address.item" and event == "string":
                meta["hospital_address"] = (meta.get("hospital_address", "") + "|" + value).strip("|")
            elif prefix == "license_information.license_number" and event == "string":
                meta["license_number"] = value
            elif prefix == "affirmation.confirm_affirmation" and event == "boolean":
                meta["confirm_affirmation"] = str(value)
            elif prefix.startswith("standard_charge_information"):
                break
    with open(src, "rb") as f, open(out, "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["hospital_name", "last_updated_on", "version", "location_name", "hospital_address",
                    "license_number", "type_2_npi", "affirmation", "confirm_affirmation"])
        w.writerow([meta.get("hospital_name", ""), meta.get("last_updated_on", ""), meta.get("version", ""),
                    meta.get("location_name", ""), meta.get("hospital_address", ""),
                    meta.get("license_number", ""), "", "", meta.get("confirm_affirmation", "")])
        w.writerow(hdr)
        for item in ijson.items(f, "standard_charge_information.item"):
            codes = item.get("code_information") or []
            codes = [(c.get("code", ""), c.get("type", "")) for c in codes][:4]
            codes += [("", "")] * (4 - len(codes))
            drug = item.get("drug_information") or {}
            desc = item.get("description", "")
            for sc in item.get("standard_charges") or []:
                base = [desc, *[x for pair in codes for x in pair],
                        "|".join(sc.get("modifiers") or []) if isinstance(sc.get("modifiers"), list) else sc.get("modifiers", ""),
                        sc.get("setting", ""), sc.get("billing_class", ""),
                        drug.get("unit", ""), drug.get("type", ""),
                        sc.get("gross_charge", ""), sc.get("discounted_cash", "")]
                tail = [sc.get("minimum", ""), sc.get("maximum", ""), "", sc.get("additional_generic_notes", "")]
                payers = sc.get("payers_information") or []
                if not payers:
                    w.writerow(base + ["", "", "", "", "", "", "", "", "", "", ""] + tail)
                for p in payers:
                    w.writerow(base + [p.get("payer_name", ""), p.get("plan_name", ""),
                                       p.get("standard_charge_dollar", ""), p.get("standard_charge_percentage", ""),
                                       p.get("standard_charge_algorithm", ""), p.get("estimated_amount", ""),
                                       p.get("median_amount", ""), p.get("10th_percentile", ""),
                                       p.get("90th_percentile", ""), p.get("count", ""), p.get("methodology", "")]
                               + [sc.get("minimum", ""), sc.get("maximum", ""),
                                  p.get("additional_payer_notes", ""), sc.get("additional_generic_notes", "")])
    return out, meta


# ----------------------------------------------------------------------------- SQL builders

def _tall_select(header: list[str]) -> str:
    unknown = [c for c in header if c not in COLMAP and c]
    if unknown:
        raise ValueError(f"unmapped tall columns {unknown}; add them to COLMAP in hospital_mrf.py")
    sel = []
    for cms, ours in COLMAP.items():
        if cms not in header:
            typ = "DOUBLE" if ours in MONEY else "INTEGER" if ours in INTS else "VARCHAR"
            sel.append(f"NULL::{typ} AS {ours}")
        elif ours in MONEY:
            sel.append(f"TRY_CAST(NULLIF(REPLACE(REPLACE(TRIM(\"{cms}\"),'$',''),',',''),'') AS DOUBLE) AS {ours}")
        elif ours in INTS:
            sel.append(f"TRY_CAST(NULLIF(TRIM(\"{cms}\"),'') AS INTEGER) AS {ours}")
        else:
            sel.append(f"NULLIF(TRIM(\"{cms}\"),'') AS {ours}")
    return ",\n    ".join(sel)


def _wide_select(header: list[str]) -> str:
    """Build a UNION ALL over the payer|plan column families of a wide file, giving the
    tall column set. Shared columns (code, gross, cash, min, max …) repeat on every branch."""
    shared, fams = {}, {}
    for h in header:
        parts = h.split("|")
        if len(parts) == 4 and parts[0] == "standard_charge" and parts[3] in WIDE_4:
            fams.setdefault((parts[1], parts[2]), {})[WIDE_4[parts[3]]] = h
        elif len(parts) == 3 and parts[0] in WIDE_3:
            fams.setdefault((parts[1], parts[2]), {})[WIDE_3[parts[0]]] = h
        elif h in COLMAP:
            shared[COLMAP[h]] = h
        elif h:
            raise ValueError(f"unmapped wide column {h!r}; extend WIDE_3/WIDE_4/COLMAP in hospital_mrf.py")
    if not fams:
        raise ValueError("wide file has no payer|plan column families")

    def col(ours, src):
        if src is None:
            typ = "DOUBLE" if ours in MONEY else "INTEGER" if ours in INTS else "VARCHAR"
            return f"NULL::{typ} AS {ours}"
        if ours in MONEY:
            return f"TRY_CAST(NULLIF(REPLACE(REPLACE(TRIM(\"{src}\"),'$',''),',',''),'') AS DOUBLE) AS {ours}"
        if ours in INTS:
            return f"TRY_CAST(NULLIF(TRIM(\"{src}\"),'') AS INTEGER) AS {ours}"
        return f"NULLIF(TRIM(\"{src}\"),'') AS {ours}"

    per_payer = {"negotiated_dollar", "negotiated_percentage", "negotiated_algorithm", "methodology",
                 "estimated_amount", "median_amount", "pct_10", "pct_90", "rate_count", "payer_notes"}
    branches = []
    for (payer, plan), cols in fams.items():
        sel = []
        for ours in COLMAP.values():
            if ours == "payer_name":
                sel.append(f"'{payer.replace(chr(39), chr(39)*2)}' AS payer_name")
            elif ours == "plan_name":
                sel.append(f"'{plan.replace(chr(39), chr(39)*2)}' AS plan_name")
            elif ours in per_payer:
                sel.append(col(ours, cols.get(ours)))
            else:
                sel.append(col(ours, shared.get(ours)))
        branches.append("SELECT " + ", ".join(sel) + " FROM r")
    # drop payer rows that carry no rate of any kind (wide files have a column for every payer on every line)
    return ("WITH r AS (SELECT * FROM _raw) SELECT * FROM (" + "\nUNION ALL\n".join(branches) + ") "
            "WHERE negotiated_dollar IS NOT NULL OR negotiated_percentage IS NOT NULL "
            "OR negotiated_algorithm IS NOT NULL OR estimated_amount IS NOT NULL")


def _derived(name: str) -> str:
    types = ", ".join(f"'{t}'" for t in CODE_TYPES[name])
    return "COALESCE(" + ", ".join(
        f"CASE WHEN upper(code_{i}_type) IN ({types}) THEN code_{i} END" for i in (1, 2, 3, 4)) + f") AS {name}"


# ----------------------------------------------------------------------------- loader

@dataclass
class MrfPart:
    """What load_release hands to the runner: one Parquet part already written by DuckDB
    (so a 4.5 M-row file never sits in Python memory). finalize/write move the parts into place."""
    ccn: str
    period: str
    path: Path
    rows: int
    columns: list[str]
    height: int = 0          # the runner reads .height only on DataFrames; kept for symmetry


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["mrf"])
    work = ctx.paths.work / "hpt"
    work.mkdir(parents=True, exist_ok=True)
    parts = work / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    src = m.local_path(ctx.paths.work)
    ccn, period = str(rel["ccn"]), str(rel["period"])

    if src.suffix.lower() == ".json":
        src, meta = json_to_tall_csv(src, work)
        _, header, skip = read_prefix(src)
        layout = "json"
    else:
        meta, header, skip = read_prefix(src)
        layout = layout_of(header)

    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET memory_limit='2GB'")

    def make_raw(path: Path) -> None:
        con.execute("DROP VIEW IF EXISTS _raw")
        con.execute(f"""CREATE VIEW _raw AS SELECT * FROM read_csv('{path.as_posix()}', skip={skip},
                        header=true, all_varchar=true, quote='"', escape='"', delim=',',
                        strict_mode=false, encoding='utf-8')""")
        con.execute("SELECT count(*) FROM _raw").fetchall()      # forces a full read now

    try:
        make_raw(src)
    except duckdb.InvalidInputException as e:
        if "not utf-8" not in str(e) and "Invalid unicode" not in str(e):
            raise
        make_raw(utf8_clean_copy(src, work, ctx))

    inner = f"SELECT {_tall_select(header)} FROM _raw" if layout in ("tall", "json") else _wide_select(header)
    con.execute(f"CREATE VIEW _t AS {inner}")

    # payer_group: classify the distinct payer/plan pairs in Python, join in DuckDB
    pairs = con.execute("SELECT DISTINCT payer_name, plan_name FROM _t").fetchall()
    con.execute("CREATE TABLE _pg (payer_name VARCHAR, plan_name VARCHAR, payer_group VARCHAR)")
    con.executemany("INSERT INTO _pg VALUES (?, ?, ?)", [(p, q, payer_group(p, q)) for p, q in pairs])

    hospital_name = meta.get("hospital_name", "")
    last_updated = meta.get("last_updated_on", "")
    last_updated_date = None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            last_updated_date = datetime.strptime(last_updated.strip()[:10], fmt).date(); break
        except ValueError:
            continue
    if last_updated_date is None:
        ctx.warn(f"{m.name}: last_updated_on {last_updated!r} not parsed")
    npis = meta.get("type_2_npi", "")
    ein = re.match(r"^(\d{2}-\d{7})", Path(m.name).name)
    affirm = next((v for k, v in meta.items() if k.lower().startswith("to the best")),
                  meta.get("affirmation") or meta.get("confirm_affirmation") or "")
    eff_start = as_date(rel.get("effective_start") or last_updated_date or f"{period}-01")
    eff_end = as_date(rel["effective_end"])

    part = parts / f"{ccn}_{period}.parquet"
    part.unlink(missing_ok=True)
    q = f"""
      COPY (
        SELECT '{ccn}' AS ccn, $hn AS hospital_name, $ein AS ein, $npis AS type2_npis,
               $ver AS mrf_version, $lu::DATE AS last_updated_on, $aff AS attestation,
               t.* EXCLUDE (setting),
               CASE lower(trim(t.setting)) WHEN 'inpatient' THEN 'Inpatient' WHEN 'outpatient' THEN 'Outpatient'
                    WHEN 'both' THEN 'Both' ELSE t.setting END AS setting,
               {_derived('hcpcs')}, {_derived('ms_drg')}, {_derived('apr_drg')},
               {_derived('rc')}, {_derived('ndc')}, {_derived('cdm')},
               g.payer_group,
               '{layout}' AS source_layout,
               DATE '{eff_start}' AS effective_start, DATE '{eff_end}' AS effective_end,
               $sf AS source_file, $sha AS source_sha256, '{period}' AS period
        FROM _t t
        LEFT JOIN _pg g ON g.payer_name IS NOT DISTINCT FROM t.payer_name
                       AND g.plan_name IS NOT DISTINCT FROM t.plan_name
      ) TO '{part.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """
    con.execute(q, {"hn": hospital_name, "ein": ein.group(1) if ein else None, "npis": npis or None,
                    "ver": meta.get("version", ""), "lu": last_updated_date, "aff": affirm or None,
                    "sf": m.lineage_name, "sha": m.sha256})
    P = f"read_parquet('{part.as_posix()}')"
    rows = con.execute(f"SELECT count(*) FROM {P}").fetchall()[0][0]
    if rows == 0:
        raise ValueError(f"{m.name}: 0 rows after parsing")
    no_code = con.execute(f"SELECT count(*) FROM {P} WHERE code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL AND code_4 IS NULL").fetchall()[0][0]
    if no_code:
        ctx.warn(f"{m.name}: {no_code} rows have no code at all")
    unmapped = con.execute(f"""SELECT count(*), list(DISTINCT code_1_type)[1:6] FROM {P}
        WHERE hcpcs IS NULL AND ms_drg IS NULL AND apr_drg IS NULL AND rc IS NULL AND ndc IS NULL AND cdm IS NULL
          AND NOT (code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL AND code_4 IS NULL)""").fetchall()[0]
    if unmapped[0]:
        ctx.warn(f"{m.name}: {unmapped[0]} rows have a code type not in CODE_TYPES: {unmapped[1]}")
    columns = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {P}").fetchall()]
    con.close()
    return ReleaseOutput(df=MrfPart(ccn, period, part, rows, columns), members=[m], raw_files=[raw])


def finalize(frames: list, ctx: Context) -> list:
    return [f for f in frames if isinstance(f, MrfPart)]


def write(parts: list, ctx: Context):
    """Move the DuckDB-written parts into data/ref/ref_hospital_mrf/<ccn>_<period>/part-000.parquet
    (atomic: build in a temp folder, then swap). build_duckdb reads the folder as one table."""
    final = ctx.paths.ref / "ref_hospital_mrf"
    tmp = ctx.paths.ref / ".ref_hospital_mrf.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    rows, columns = 0, []
    for p in parts:
        d = tmp / f"{p.ccn}_{p.period}"
        d.mkdir()
        shutil.move(str(p.path), d / "part-000.parquet")
        rows += p.rows
        columns = columns or p.columns
    missing = [c for c in LINEAGE_COLS if c not in columns]
    if missing:
        raise ValueError(f"ref_hospital_mrf missing lineage columns {missing}")
    shutil.rmtree(final, ignore_errors=True)
    (ctx.paths.ref / "ref_hospital_mrf.parquet").unlink(missing_ok=True)
    tmp.rename(final)
    return final, rows, columns
