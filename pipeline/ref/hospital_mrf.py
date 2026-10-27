"""Step 2 â€” ref_hospital_mrf: hospital price transparency files (45 CFR 180 machine-readable files).

One release = one hospital (CCN) Ã— one download period. The release in
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
  * CSV "tall"  (one row per code Ã— payer Ã— plan)                    v2.x and v3.x
  * CSV "wide"  (one row per code, one column family per payer|plan)  v2.x and v3.x
  * JSON        (standard_charge_information[] â†’ standard_charges[] â†’ payers_information[])
JSON is streamed with ijson into a tall CSV in data/work, then read like a tall CSV.

Every row carries the hospital block (ccn, hospital_name, ein, type2_npis, mrf_version,
last_updated_on), the derived join keys (hcpcs, ms_drg, apr_drg, rc, ndc, cdm), a cleaned
payer_group (config/payer_groups.yaml) and the lineage columns.
"""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import polars as pl

from ..common import config
from ..common.raw import RawFileMissing
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
    # seen in the wild (Cleveland Clinic, Oct 2026): same meaning, other header text
    "count_of_compared_rates": "rate_count",
    "footnote": "notes",
    "payer_notes": "payer_notes",
    "generic_notes": "notes",
}
# header text is matched after lower-casing and trimming; "Median_amount|Aetna|..." = "median_amount|aetna|..."


_PIPE_WS = re.compile(r"\s*\|\s*")


def norm(h: str) -> str:
    """Lower-case, trim, and drop spaces around "|" ("Code | 1" = "code|1"; Blanchard Valley and Western Reserve write it so)."""
    return _PIPE_WS.sub("|", (h or "").strip().lower())


def unknown_columns(header: list[str]) -> list[str]:
    """Columns outside the template. They are ignored (with a warning), never a reason to stop."""
    out = []
    for h in header:
        n = norm(h)
        if not n or n in COLMAP:
            continue
        parts = n.split("|")
        if len(parts) == 4 and parts[0] == "standard_charge" and parts[3] in WIDE_4:
            continue
        if len(parts) == 3 and parts[0] in WIDE_3:
            continue
        out.append(h)
    return out
MONEY = {"gross_charge", "discounted_cash", "negotiated_dollar", "negotiated_percentage",
         "estimated_amount", "median_amount", "pct_10", "pct_90", "charge_min", "charge_max"}
INTS = {"rate_count"}
# wide layout: metric names that appear as "<metric>|payer|plan" (3 parts)
WIDE_3 = {"estimated_amount": "estimated_amount", "additional_payer_notes": "payer_notes",
          "median_amount": "median_amount", "10th_percentile": "pct_10", "90th_percentile": "pct_90",
          "count": "rate_count", "count_of_compared_rates": "rate_count", "footnote": "payer_notes",
          "payer_notes": "payer_notes"}
# wide layout: "standard_charge|payer|plan|<metric>" (4 parts)
WIDE_4 = {"negotiated_dollar": "negotiated_dollar", "negotiated_percentage": "negotiated_percentage",
          "negotiated_algorithm": "negotiated_algorithm", "methodology": "methodology"}
CODE_TYPES = {  # derived join column -> code types that feed it
    "hcpcs": ("HCPCS", "CPT"), "ms_drg": ("MS-DRG",), "apr_drg": ("APR-DRG",), "rc": ("RC",),
    "ndc": ("NDC",), "cdm": ("CDM", "LOCAL"),
    # code systems we keep but do not price with (rehab DRGs, outpatient groupers, diagnoses)
    "code_other": ("R-DRG", "CMG", "EAPG", "APC", "ICD", "ICD-10", "ICD10", "ICD-10-CM", "ICD-10-PCS", "TRICARE", "HIPPS", "ASC",
                  "DRG", "TRIS-DRG"),
}
# Some hospitals (Mercy Health) write the code type as a bare "DRG". A bare DRG with an APR severity word at the end of
# the description ("... PROCEDURE,MODERATE") is an APR-DRG (code + severity of illness). A bare DRG without one stays
# in code_other (it can be an MS-DRG or an APR-DRG; the pricing step decides by payer). Nothing is guessed silently.
_APR_SOI = r"regexp_matches(upper(description), ',\s*(MINOR|MODERATE|MAJOR|EXTREME)\s*$')"

_payer_rules: list[tuple[re.Pattern, str]] | None = None


def payer_group_rules() -> list[tuple[re.Pattern, str]]:
    global _payer_rules
    if _payer_rules is None:
        rules = config.load_yaml("payer_groups.yaml")["groups"]
        _payer_rules = [(re.compile(r["match"], re.I), r["group"]) for r in rules]
    return _payer_rules


def payer_group(payer: str | None, plan: str | None) -> str:
    text = f"{payer or ''} {plan or ''}"
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
    low = [norm(h) for h in header]
    if "payer_name" in low:
        return "tall"
    if any(h.startswith("standard_charge|") and h.count("|") == 3 for h in low) or \
       any(h.split("|")[0] in WIDE_3 and h.count("|") == 2 for h in low):
        return "wide"
    raise ValueError(f"unknown CSV layout; header starts {header[:8]}")


# ----------------------------------------------------------------------------- JSON -> tall CSV

def json_clean_copy(src: Path, work: Path) -> Path:
    """ijson needs clean UTF-8 without a BOM. UTF-8 BOM: skip it. UTF-16 (seen from Windows
    exports): transcode to a UTF-8 copy in work/. Anything else: returned unchanged."""
    with open(src, "rb") as f:
        head = f.read(4)
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        out = work / (src.stem + ".utf8.json")
        with open(src, "r", encoding="utf-16") as fi, open(out, "w", encoding="utf-8") as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
        return out
    if head[:3] == b"\xef\xbb\xbf" or (head[:1] not in (b"{", b"[") and head.lstrip()[:1] in (b"{", b"[")):
        out = work / (src.stem + ".utf8.json")
        with open(src, "rb") as fi, open(out, "wb") as fo:
            first = fi.read(1 << 20)
            first = first[3:] if first[:3] == b"\xef\xbb\xbf" else first.lstrip()
            fo.write(first)
            shutil.copyfileobj(fi, fo, 1 << 20)
        return out
    return src


def json_to_tall_csv(src: Path, work: Path) -> tuple[Path, dict]:
    """Stream a CMS JSON file (v2.x/v3.x) into a tall CSV with the same header the CSV
    template uses, so one reader serves both. Returns (csv_path, hospital_meta)."""
    import ijson
    src = json_clean_copy(src, work)
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
    by_norm = {}
    for h in header:
        by_norm.setdefault(norm(h), h)          # original text, for quoting in SQL
    src_for: dict[str, str] = {}                # ours -> header text
    for cms, ours in COLMAP.items():
        if cms in by_norm and ours not in src_for:
            src_for[ours] = by_norm[cms]
    sel = []
    for ours in dict.fromkeys(COLMAP.values()):
        cms = src_for.get(ours)
        if cms is None:
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
    tall column set. Shared columns (code, gross, cash, min, max â€¦) repeat on every branch."""
    shared, fams = {}, {}
    for h in header:
        n = norm(h)
        parts = n.split("|")
        raw_parts = h.strip().split("|")
        if len(parts) == 4 and parts[0] == "standard_charge" and parts[3] in WIDE_4:
            fams.setdefault((raw_parts[1].strip(), raw_parts[2].strip()), {}).setdefault(WIDE_4[parts[3]], h)
        elif len(parts) == 3 and parts[0] in WIDE_3:
            fams.setdefault((raw_parts[1].strip(), raw_parts[2].strip()), {}).setdefault(WIDE_3[parts[0]], h)
        elif n in COLMAP:
            shared.setdefault(COLMAP[n], h)
        # anything else: outside the template, ignored (unknown_columns() reports it)
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
        for ours in dict.fromkeys(COLMAP.values()):
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

    def cond(i: int) -> str:
        t = f"upper(code_{i}_type)"
        if name == "apr_drg":
            return f"({t} IN ({types}) OR ({t} = 'DRG' AND {_APR_SOI}))"
        if name == "code_other":
            return f"({t} IN ({types}) AND NOT ({t} = 'DRG' AND {_APR_SOI}))"
        return f"{t} IN ({types})"
    return "COALESCE(" + ", ".join(f"CASE WHEN {cond(i)} THEN code_{i} END" for i in (1, 2, 3, 4)) + f") AS {name}"


# ----------------------------------------------------------------------------- loader

@dataclass
class MrfPart:
    ccn: str
    period: str
    path: Path
    rows: int
    columns: list[str]
    height: int = 0
    meta: dict = field(default_factory=dict)      # per-release manifest fields (hospital_name, hashes, layout...)


class ReleaseQuarantined(RawFileMissing):
    """A release whose file cannot be parsed. Subclass of RawFileMissing so the runner records it
    as 'skipped' and goes on with the other hospitals (one bad file never blocks the table)."""


def quarantine_path(ctx: Context, ccn: str, period: str) -> Path:
    d = ctx.paths.manifests / "ref_hospital_mrf"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{ccn}_{period}.quarantine.json"


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["mrf"])
    ccn, period = str(rel["ccn"]), str(rel["period"])
    try:
        out = _load_release(rel, ctx, raw, m)
    except RawFileMissing:
        raise
    except Exception as e:  # noqa: BLE001  â€” parse/format problem in THIS file only
        err = f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
        quarantine_path(ctx, ccn, period).write_text(json.dumps(
            {"table": "ref_hospital_mrf", "ccn": ccn, "period": period, "file": rel["file"], "member": m.name,
             "stage": "load", "error": err, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2), encoding="utf-8")
        ctx.warn(f"QUARANTINED {ccn} {period} ({m.name}): {err}")
        raise ReleaseQuarantined(f"quarantined {ccn} {period}: {err}") from e
    quarantine_path(ctx, ccn, period).unlink(missing_ok=True)      # a good load clears an old quarantine
    return out


def _load_release(rel: dict, ctx: Context, raw, m) -> ReleaseOutput:
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
    con.execute("SET memory_limit='8GB'")
    con.execute("SET threads=2")
    def make_raw(path: Path, pad: bool = False, ign: bool = False) -> None:
        con.execute("DROP VIEW IF EXISTS _raw")
        opt = ("null_padding=true, " if pad else "") + ("ignore_errors=true, store_rejects=true, " if ign else "")
        con.execute(f"""CREATE VIEW _raw AS SELECT * FROM read_csv('{path.as_posix()}', skip={skip},
                        header=true, all_varchar=true, quote='"', escape='"', delim=',',
                        strict_mode=false, {opt}encoding='utf-8')""")
        try:
            con.execute("SELECT max(length(COLUMNS(*))) FROM _raw").fetchall()   # parses every column
        except duckdb.OutOfMemoryException:
            pass
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

    extra = unknown_columns(header)
    if extra:
        ctx.warn(f"{m.name}: {len(extra)} column(s) outside the CMS template ignored: {extra[:8]}")
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
               {_derived('rc')}, {_derived('ndc')}, {_derived('cdm')}, {_derived('code_other')},
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
        WHERE hcpcs IS NULL AND ms_drg IS NULL AND apr_drg IS NULL AND rc IS NULL AND ndc IS NULL AND cdm IS NULL AND code_other IS NULL
          AND NOT (code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL AND code_4 IS NULL)""").fetchall()[0]
    if unmapped[0]:
        ctx.warn(f"{m.name}: {unmapped[0]} rows have a code type not in CODE_TYPES: {unmapped[1]}")
    bare = con.execute(f"""SELECT count(*) FILTER (WHERE upper(code_1_type) = 'DRG' AND apr_drg IS NOT NULL),
                                  count(*) FILTER (WHERE upper(code_1_type) = 'DRG' AND apr_drg IS NULL) FROM {P}""").fetchall()[0]
    if bare[0] or bare[1]:
        ctx.warn(f"{m.name}: bare 'DRG' code type: {bare[0]} rows read as APR-DRG (severity word in description), {bare[1]} rows kept in code_other")
    columns = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {P}").fetchall()]
    payers = con.execute(f"SELECT count(DISTINCT payer_name) FROM {P}").fetchall()[0][0]
    con.close()
    meta_out = {"table": "ref_hospital_mrf", "ccn": ccn, "period": period, "hospital_name": hospital_name,
                "ein": ein.group(1) if ein else None, "type2_npis": npis or None, "mrf_version": meta.get("version", ""),
                "last_updated_on": str(last_updated_date) if last_updated_date else None, "layout": layout,
                "rows": rows, "payers": payers, "no_code_rows": no_code, "unmapped_code_rows": unmapped[0],
                "file": rel["file"], "member": m.name, "source_file": m.lineage_name, "source_sha256": m.sha256,
                "raw_sha256": raw.sha256, "effective_start": str(eff_start), "effective_end": str(eff_end),
                "page": rel.get("page"), "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return ReleaseOutput(df=MrfPart(ccn, period, part, rows, columns, meta=meta_out), members=[m], raw_files=[raw])


def finalize(frames: list, ctx: Context) -> list:
    return [f for f in frames if isinstance(f, MrfPart)]


def write(parts: list, ctx: Context):
    """Put each loaded release at data/ref/ref_hospital_mrf/<ccn>_<period>/part-000.parquet and write
    its manifest at data/ref/_manifest/ref_hospital_mrf/<ccn>_<period>.json.

    Releases NOT in this run are left in place, so `load_ref ref_hospital_mrf --period 2026-11`
    adds a month without reloading 90 hospitals. When the run covered every configured release
    (a full load), folders that no longer belong to any release are removed. Each folder swap is
    atomic (write beside, then rename). Returns the row count of the WHOLE table."""
    final = ctx.paths.ref / "ref_hospital_mrf"
    final.mkdir(parents=True, exist_ok=True)
    (ctx.paths.ref / "ref_hospital_mrf.parquet").unlink(missing_ok=True)
    man_dir = ctx.paths.manifests / "ref_hospital_mrf"
    man_dir.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for p in parts:
        columns = columns or p.columns
        missing = [c for c in LINEAGE_COLS if c not in p.columns]
        if missing:
            raise ValueError(f"ref_hospital_mrf {p.ccn} {p.period}: missing lineage columns {missing}")
        d = final / f"{p.ccn}_{p.period}"
        tmp = final / f".{p.ccn}_{p.period}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        shutil.move(str(p.path), tmp / "part-000.parquet")
        shutil.rmtree(d, ignore_errors=True)
        tmp.rename(d)
        (man_dir / f"{p.ccn}_{p.period}.json").write_text(json.dumps(p.meta, indent=2, default=str), encoding="utf-8")
    expected = {f"{r['ccn']}_{r['period']}" for r in ctx.spec.get("releases", [])}
    loaded = {f"{p.ccn}_{p.period}" for p in parts}
    if loaded >= expected:                       # full load: drop folders of releases removed from the yaml
        for d in final.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name not in expected:
                shutil.rmtree(d, ignore_errors=True)
                (man_dir / f"{d.name}.json").unlink(missing_ok=True)
    rows = 0
    con = duckdb.connect()
    for d in sorted(final.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            rows += con.execute(f"SELECT count(*) FROM read_parquet('{(d / 'part-000.parquet').as_posix()}')").fetchall()[0][0]
    if not columns:
        columns = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{final.as_posix()}/**/*.parquet', union_by_name=true)").fetchall()]
    con.close()
    return final, rows, columns


