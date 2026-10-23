"""Check that the downloads are in the right place, BEFORE loading.

For every release in config/sources.yaml it checks: the file exists, it
opens (zip / xlsx), each file the loader needs is inside it, and (NPPES) the
header has every column. It does not hash or load anything, so it is fast.

    python -m pipeline.check_raw          # or: manage.py check_raw
"""
from __future__ import annotations

import sys

from .common import config
from .common.raw import RawFile, RawFileMissing

OK, MISSING, BAD = "OK", "MISSING", "PROBLEM"


def _files(rel: dict) -> list:
    """Each item is one path, or a list of choices (first found wins)."""
    if "files" in rel:
        return list(rel["files"])
    return [rel["file"]]


def _open(paths, choices) -> tuple[RawFile | None, str]:
    opts = [choices] if isinstance(choices, str) else list(choices)
    for c in opts:
        try:
            return RawFile(paths.raw, c), c
        except RawFileMissing:
            continue
    return None, " or ".join(opts)


def check(data_root: str | None = None) -> list[tuple[str, str, str, str]]:
    paths = config.data_paths(data_root)
    rows = []
    for table, spec in config.sources().items():
        for rel in spec["releases"]:
            label = str(rel["period"]) + (f"/{rel['setting']}" if rel.get("setting") else "")
            items = _files(rel) + ([rel["deactivation_file"]] if rel.get("deactivation_file") else [])
            for choices in items:
                raw, name = _open(paths, choices)
                if raw is None:
                    rows.append((table, label, MISSING, f"put it at {(paths.raw / name).as_posix()}"))
                    continue
                problems = []
                try:
                    names = raw.names()
                except Exception as e:  # noqa: BLE001
                    rows.append((table, label, BAD, f"{name}: cannot open ({e})"))
                    continue
                if choices == rel.get("deactivation_file"):
                    if not any(n.lower().endswith((".xlsx", ".csv")) for n in names):
                        problems.append("no .xlsx/.csv inside")
                else:
                    for key, pattern in (rel.get("members") or {}).items():
                        if key == "header":
                            continue
                        hits = raw.members(pattern)
                        if key == "addendum_b":
                            hits = [m for m in hits if m.name.lower().endswith((".csv", ".xlsx"))]
                            if not hits:
                                problems.append("no Addendum B .csv/.xlsx inside")
                            continue
                        if len(hits) != 1:
                            problems.append(f"'{key}' ({pattern}) matched {len(hits)} files")
                    if table == "ref_provider" and not problems:
                        problems += _check_nppes_header(raw, rel)
                if problems:
                    rows.append((table, label, BAD, f"{name}: " + "; ".join(problems)))
                else:
                    size = raw.size_bytes / 1e6
                    rows.append((table, label, OK, f"{name} ({size:,.1f} MB)"))
    return rows


def _check_nppes_header(raw: RawFile, rel: dict) -> list[str]:
    from .ref.nppes import read_header, resolve_columns
    hdr = raw.members(rel["members"].get("header", "__none__"))
    m = hdr[0] if hdr else raw.member(rel["members"]["main"])
    _, opt, missing = resolve_columns(read_header(m))
    if missing:
        return [f"header missing {len(missing)} columns, e.g. {missing[:3]}"]
    return []


def render(rows) -> str:
    w = max(len(r[0]) for r in rows) if rows else 10
    out = [f"{'table':{w}s}  {'release':22s}  {'status':8s}  detail", "-" * (w + 60)]
    out += [f"{t:{w}s}  {p:22s}  {s:8s}  {d}" for t, p, s, d in rows]
    n = {k: sum(1 for r in rows if r[2] == k) for k in (OK, MISSING, BAD)}
    out += ["", f"{n[OK]} OK, {n[MISSING]} missing, {n[BAD]} problem"]
    if n[BAD]:
        out.append("Fix every PROBLEM line before load_ref. MISSING files are skipped by load_ref.")
    return "\n".join(out)


def main() -> int:
    rows = check()
    print(render(rows))
    return 1 if any(r[2] == BAD for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
