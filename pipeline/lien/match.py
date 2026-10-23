"""Find the hospital (CCN) of a bill: by CCN, then NPI, then name."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .db import objects, rows


@dataclass
class HospitalMatch:
    ccn: str
    name: str
    npi: str
    method: str          # ccn | npi | name
    certain: bool        # False = a person must confirm it


_STOPWORDS = {"the", "of", "and", "inc", "llc", "hospital", "hospitals", "medical", "center", "health", "system", "at"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split() if t not in _STOPWORDS}


def _name_for_ccn(con, have: set[str], ccn: str) -> str:
    for table, col in (("ref_hospital_mrf", "hospital_name"), ("ref_ipps_hospital", "hospital_name"),
                       ("ref_ccn_npi", "organization_name")):
        if table in have:
            r = rows(con, f"SELECT {col} AS n FROM {table} WHERE ccn = ? AND {col} IS NOT NULL LIMIT 1", [ccn])
            if r:
                return r[0]["n"]
    return ""


def find(con, ccn: str = "", npi: str = "", name: str = "") -> HospitalMatch | None:
    have = objects(con)
    if ccn:
        found = _name_for_ccn(con, have, ccn)
        if found:
            return HospitalMatch(ccn, found, npi, "ccn", True)
    if npi and "ref_ccn_npi" in have:
        r = rows(con, "SELECT DISTINCT ccn, organization_name FROM ref_ccn_npi WHERE CAST(npi AS VARCHAR) = ?", [npi])
        if len(r) == 1:
            return HospitalMatch(r[0]["ccn"], r[0]["organization_name"] or "", npi, "npi", True)
    if npi and "ref_hospital_mrf" in have:
        r = rows(con, "SELECT DISTINCT ccn, hospital_name FROM ref_hospital_mrf WHERE type2_npis LIKE ?", [f"%{npi}%"])
        if len(r) == 1:
            return HospitalMatch(r[0]["ccn"], r[0]["hospital_name"] or "", npi, "npi", True)
    want = _tokens(name)
    if not want:
        return None
    cands: dict[str, str] = {}
    if "ref_hospital_mrf" in have:
        cands.update({r["ccn"]: r["n"] for r in rows(con, "SELECT DISTINCT ccn, hospital_name AS n FROM ref_hospital_mrf")})
    if "ref_ccn_npi" in have:
        for r in rows(con, "SELECT DISTINCT ccn, coalesce(dba_name, organization_name) AS n FROM ref_ccn_npi WHERE state = 'OH'"):
            cands.setdefault(r["ccn"], r["n"])
    scored = []
    for c, n in cands.items():
        got = _tokens(n)
        if got:
            scored.append((len(want & got) / len(want | got), c, n))
    scored.sort(reverse=True)
    if scored and scored[0][0] >= 0.6 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
        return HospitalMatch(scored[0][1], scored[0][2], npi, "name", False)
    return None
