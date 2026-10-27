"""Put the ref_hospital_mrf block of config/sources_local.yaml back to a known state.

  python tools/hpt_reset_yaml.py            # keep the block, but re-add OSU + James from config/sources_hpt_snippet.yaml if missing
  python tools/hpt_reset_yaml.py --fresh    # replace the whole block with the snippet (OSU + James only)

Also clears stale quarantine records and the D:\\...\\data\\raw\\MRF copies made when MESHKOR_RAW_DIR was
not visible to the pipeline (before Oct 23 fix). Raw files on E:\\ are never touched.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.common import config  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--fresh", action="store_true"); a = ap.parse_args()
yaml_p = ROOT / "config" / "sources_local.yaml"
snip = (ROOT / "config" / "sources_hpt_snippet.yaml").read_text(encoding="utf-8")
text = yaml_p.read_text(encoding="utf-8")
block = re.search(r"^ref_hospital_mrf:.*?(?=^\S|\Z)", text, re.S | re.M)
if a.fresh or not block:
    text = (text[:block.start()] + text[block.end():] if block else text).rstrip() + "\n\n" + snip
    print("ref_hospital_mrf block replaced with the snippet (OSU + James)")
else:
    b = block.group(0)
    for ccn in ("360085", "360242"):
        if f'ccn: "{ccn}"' not in b:
            rel = re.search(r'^  - period: "2026-10"\n    ccn: "' + ccn + r'".*?(?=^  - |\Z)', snip, re.S | re.M).group(0)
            b = re.sub(r"(  releases:\s*\n)", r"\1" + rel.replace("\\", "\\\\"), b, count=1)
            print(f"re-added {ccn}")
    text = text[:block.start()] + b + text[block.end():]
yaml_p.write_text(text, encoding="utf-8")
paths = config.data_paths()
for q in (paths.manifests / "ref_hospital_mrf").glob("*.quarantine.json"):
    q.unlink(); print(f"removed {q.name}")
q = paths.ref / "_quarantine"
if q.exists():
    shutil.rmtree(q); print("removed data/ref/_quarantine (everything there is reloadable from the raw files)")
wrong = ROOT / "data" / "raw" / "MRF"
if wrong.exists() and Path(paths.raw).resolve() != (ROOT / "data" / "raw").resolve():
    shutil.rmtree(wrong); print(f"removed wrong copies at {wrong}")
print(f"raw dir in use: {paths.raw}")
print("next:  python backend\\manage.py load_ref ref_hospital_mrf  &&  build_duckdb  &&  python -m pipeline.hpt.verify")
