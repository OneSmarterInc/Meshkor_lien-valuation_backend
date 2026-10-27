r"""Register downloaded MRF files whose names have NO CCN, by matching the file name to the hospital
names in data\ref\hpt_hospitals.parquet. Dry run by default.

  python tools\intake_by_name.py --source "G:\Hansawahini2" --member member4
  python tools\intake_by_name.py --source "G:\Hansawahini2" --member member4 --run --load
  --set 451441844=360xxx   force a CCN for files whose name starts with that text (repeatable)
Originals in --source are never touched: each file is copied to a stage folder first.
"""
import argparse, os, re, shutil, subprocess, sys
from pathlib import Path
import polars as pl

STOP = set("standardcharges standard charges charge csv json xlsx xls zip inc llc lp the of and hospital hospitals "
           "medical center centre health system systems services corp ltd association mrf pt x city".split())
DATA = {".csv", ".json", ".zip", ".xlsx", ".xls", ".txt"}


def toks(s):
    return {t for t in re.findall(r"[a-z]+", s.lower()) if t not in STOP and len(t) > 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True); ap.add_argument("--period", default="2026-10")
    ap.add_argument("--member", default="member"); ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--run", action="store_true"); ap.add_argument("--load", action="store_true")
    a = ap.parse_args()
    root = Path.cwd()
    forced = dict(x.split("=", 1) for x in a.set)
    hosp = pl.read_parquet(root / "data" / "ref" / "hpt_hospitals.parquet").select("ccn", "hospital_name", "city", "npi", "all_npis").to_dicts()
    for h in hosp:
        h["t"] = toks((h["hospital_name"] or "") + " " + (h["city"] or ""))
        h["n"] = {str(x) for x in (h.get("all_npis") or [])} | ({str(h["npi"])} if h.get("npi") else set())
    have = {p.name for p in (root / "data" / "ref" / "ref_hospital_mrf").glob("*")} if (root / "data/ref/ref_hospital_mrf").exists() else set()
    files = sorted(p for p in Path(a.source).iterdir() if p.is_file() and p.suffix.lower() in DATA)
    plan = []
    for f in files:
        m = re.match(r"^(\d{6})__", f.name)
        why = ""
        if m:
            ccn = m.group(1); why = "ccn in name"
        else:
            ccn = next((v for k, v in forced.items() if f.name.startswith(k)), None)
            if ccn: why = "forced"
            else:
                nums = set(re.findall(r"(?<!\d)\d{10}(?!\d)", f.name))
                hit = [h for h in hosp if nums & h["n"]]
                if len({h["ccn"] for h in hit}) == 1:
                    ccn = hit[0]["ccn"]; why = f"NPI match: {hit[0]['hospital_name']}"
            if not ccn:
                ft = toks(re.sub(r"^[\d\-_]+", "", f.stem))
                sc = sorted(((len(ft & h["t"]) / max(1, len(ft | h["t"])), h) for h in hosp if ft & h["t"]),
                            key=lambda x: -x[0])
                if sc and sc[0][0] >= 0.5 and (len(sc) == 1 or sc[0][0] - sc[1][0] >= 0.1):
                    ccn = sc[0][1]["ccn"]; why = f"name match {sc[0][0]:.2f}: {sc[0][1]['hospital_name']}"
                else:
                    why = "AMBIGUOUS: " + "; ".join(f"{h['ccn']} {h['hospital_name']} ({s:.2f})" for s, h in sc[:3])
        plan.append((f, ccn, why))
    print(f"{'file':60} {'MB':>8}  {'ccn':7} parquet  how")
    for f, ccn, why in plan:
        print(f"{f.name[:60]:60} {f.stat().st_size/1e6:8.1f}  {ccn or '-':7} {'yes' if ccn in have else 'no ':7}  {why}")
    todo = [(f, c) for f, c, _ in plan if c]
    if not a.run:
        print("\nDry run. Check the table, then add --run (and --load). Fix AMBIGUOUS rows with --set <file-start>=<ccn>.")
        return
    env = dict(os.environ, PYTHONPATH=str(root))
    stage = root / "data" / "work" / "_stage"; ok = []
    for f, ccn in todo:
        shutil.rmtree(stage, ignore_errors=True); stage.mkdir(parents=True)
        dst = stage / f.name; shutil.copy2(f, dst)
        r = subprocess.run([sys.executable, "-m", "pipeline.hpt.intake", "--period", a.period, "--ccn", ccn,
                            "--file", str(dst), "--page", a.member, "--write-yaml"], env=env, cwd=root)
        print(("OK    " if r.returncode == 0 else "FAILED"), ccn, f.name)
        if r.returncode == 0: ok.append(ccn)
    shutil.rmtree(stage, ignore_errors=True)
    ccns = ",".join(sorted(set(ok)))
    cmd = [sys.executable, "backend/manage.py", "load_ref", "ref_hospital_mrf", "--period", a.period, "--ccn", ccns]
    print("\nregistered:", ccns)
    if a.load and ccns:
        subprocess.run(cmd, env=env, cwd=root)
    else:
        print("next:", "python backend\\manage.py load_ref ref_hospital_mrf --period", a.period, "--ccn", ccns)

main()