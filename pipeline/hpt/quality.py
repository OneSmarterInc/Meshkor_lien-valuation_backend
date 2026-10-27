"""Guide 2.4 step 4: per-hospital quality report for a loaded price file.

Reads data/ref/ref_hospital_mrf (the loader's output) and writes
data/reports/hpt_quality_<ccn>_<period>.md with: rows, codes, payers and plans, rows with
no rate of any kind, percentage-only rows, algorithm-only rows, cash price presence,
percentile presence, code types, top payers, and the rows the loader could not map.

Run:  python -m pipeline.hpt.quality --ccn 360085 --period 2026-10     (or --all)
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ..common import config


def report(ccn: str, period: str, paths, con) -> Path:
    T = f"read_parquet('{(paths.ref / 'ref_hospital_mrf').as_posix()}/**/*.parquet', union_by_name=true)"
    base = f"(SELECT * FROM {T} WHERE ccn = '{ccn}' AND period = '{period}')"
    one = lambda sql: con.execute(sql.replace("__T__", base)).fetchone()
    n = one("SELECT count(*) FROM __T__")[0]
    if n == 0:
        raise SystemExit(f"no rows for ccn={ccn} period={period}")
    meta = one("SELECT any_value(hospital_name), any_value(mrf_version), any_value(last_updated_on), any_value(source_layout), any_value(source_file), any_value(source_sha256), any_value(attestation) FROM __T__")
    stats = one("""SELECT count(DISTINCT hcpcs), count(DISTINCT ms_drg), count(DISTINCT apr_drg), count(DISTINCT rc),
                          count(DISTINCT ndc), count(DISTINCT cdm), count(DISTINCT payer_name), count(DISTINCT plan_name),
                          count(DISTINCT payer_group) FROM __T__""")
    rates = one("""SELECT
        sum(CASE WHEN negotiated_dollar IS NULL AND negotiated_percentage IS NULL AND negotiated_algorithm IS NULL AND estimated_amount IS NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN negotiated_dollar IS NOT NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN negotiated_dollar IS NULL AND negotiated_percentage IS NOT NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN negotiated_dollar IS NULL AND negotiated_percentage IS NULL AND negotiated_algorithm IS NOT NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN estimated_amount IS NOT NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN discounted_cash IS NOT NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN gross_charge IS NOT NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN median_amount IS NOT NULL OR pct_10 IS NOT NULL OR pct_90 IS NOT NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN negotiated_dollar < 0 OR gross_charge < 0 THEN 1 ELSE 0 END),
        sum(CASE WHEN negotiated_dollar IS NOT NULL AND negotiated_dollar < 5 AND gross_charge >= 50 THEN 1 ELSE 0 END),
        sum(CASE WHEN code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL AND code_4 IS NULL THEN 1 ELSE 0 END),
        sum(CASE WHEN hcpcs IS NULL AND ms_drg IS NULL AND apr_drg IS NULL AND rc IS NULL AND ndc IS NULL AND cdm IS NULL AND COALESCE(code_other, NULL) IS NULL THEN 1 ELSE 0 END)
        FROM __T__""")
    settings = con.execute(f"SELECT setting, count(*) FROM {base} GROUP BY 1 ORDER BY 2 DESC").fetchall()
    types = con.execute(f"""SELECT t, count(*) FROM (SELECT code_1_type t FROM {base} UNION ALL SELECT code_2_type FROM {base}
                             UNION ALL SELECT code_3_type FROM {base}) WHERE t IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    payers = con.execute(f"""SELECT payer_group, count(DISTINCT payer_name || '|' || coalesce(plan_name,'')) AS plans, count(*) AS rows_,
                              sum(CASE WHEN negotiated_dollar IS NOT NULL THEN 1 ELSE 0 END) AS dollar_rows
                              FROM {base} GROUP BY 1 ORDER BY 3 DESC""").fetchall()
    other = con.execute(f"SELECT payer_name, plan_name, count(*) FROM {base} WHERE payer_group = 'Other' GROUP BY 1,2 ORDER BY 3 DESC LIMIT 15").fetchall()
    pct = lambda x: f"{x:,} ({100*x/n:.1f} %)"
    lines = [f"# Price file quality: {meta[0]} (CCN {ccn}), period {period}", "",
             f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}. Template v{meta[1]}, layout {meta[3]}, "
             f"file dated {meta[2]}. Source `{meta[4]}` SHA-256 `{meta[5]}`. Attestation: {'present' if meta[6] else 'missing'}.", "",
             "| Measure | Value |", "|---|---|",
             f"| Rows (code × payer × plan) | {n:,} |",
             f"| Distinct HCPCS/CPT · MS-DRG · APR-DRG · revenue codes · NDC · CDM | {stats[0]:,} · {stats[1]:,} · {stats[2]:,} · {stats[3]:,} · {stats[4]:,} · {stats[5]:,} |",
             f"| Payers · plans · payer groups | {stats[6]} · {stats[7]} · {stats[8]} |",
             f"| Rows with a dollar rate | {pct(rates[1])} |",
             f"| Rows with percentage only | {pct(rates[2])} |",
             f"| Rows with algorithm only | {pct(rates[3])} |",
             f"| Rows with an estimated amount | {pct(rates[4])} |",
             f"| Rows with **no rate of any kind** | {pct(rates[0])} |",
             f"| Rows with a cash price | {pct(rates[5])} |",
             f"| Rows with a gross charge | {pct(rates[6])} |",
             f"| Rows with percentiles (2026 rule) | {pct(rates[7])} |",
             f"| Negative prices | {rates[8]:,} |",
             f"| Dollar rate under $5 on a charge of $50+ (likely a multiplier posted as dollars; report as percentage) | {pct(rates[9])} |",
             f"| Rows with no code | {rates[10]:,} |",
             f"| Rows whose code type is not mapped | {rates[11]:,} |", "",
             "## Settings", "", "| Setting | Rows |", "|---|---|"] + [f"| {s} | {c:,} |" for s, c in settings] + [
             "", "## Code types", "", "| Type | Occurrences |", "|---|---|"] + [f"| {t} | {c:,} |" for t, c in types] + [
             "", "## Payer groups", "", "| Group | Plans | Rows | Rows with $ |", "|---|---|---|---|"] + [
             f"| {g} | {p} | {r:,} | {d:,} |" for g, p, r, d in payers]
    if other:
        lines += ["", "## Payers mapped to Other (add rules to config/payer_groups.yaml)", "", "| Payer | Plan | Rows |", "|---|---|---|"]
        lines += [f"| {p} | {q} | {c:,} |" for p, q, c in other]
    out = paths.root / "reports" / f"hpt_quality_{ccn}_{period}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{ccn} {period}: {n:,} rows, no-rate {rates[0]:,}, cash {rates[5]:,} -> {out}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ccn"); ap.add_argument("--period"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    paths = config.data_paths(a.data_root)
    con = duckdb.connect()
    if a.all:
        T = f"read_parquet('{(paths.ref / 'ref_hospital_mrf').as_posix()}/**/*.parquet', union_by_name=true)"
        for ccn, period in con.execute(f"SELECT DISTINCT ccn, period FROM {T} ORDER BY 1, 2").fetchall():
            report(ccn, period, paths, con)
    else:
        if not (a.ccn and a.period):
            ap.error("--ccn and --period, or --all")
        report(a.ccn, a.period, paths, con)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
