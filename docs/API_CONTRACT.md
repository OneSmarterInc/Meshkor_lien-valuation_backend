# MeshKor Lien Valuation: API contract (frontend ⇄ backend)

Version 1 · 2026-10-23. The React frontend calls exactly these endpoints. Build the backend to match, or change `src/api/endpoints.js` in one place if a path differs.

## General rules

| Rule | Value |
|---|---|
| Base URL | `VITE_API_BASE_URL` (e.g. `https://api.meshkor.com`). In development, Vite proxies `/api` to `http://localhost:8000`. |
| Format | JSON, `snake_case` keys (Django REST Framework default). Dates `YYYY-MM-DD`, timestamps ISO 8601 with time zone. Money = number in US dollars (not a string). |
| Auth | `Authorization: Bearer <access>` on every call except login and refresh (SimpleJWT style). |
| Token expiry | On `401`, the frontend calls refresh once, then repeats the request. If refresh fails, it logs out. |
| Errors | Status code + JSON `{"detail": "message"}` or DRF field errors `{"field": ["message"]}`. The frontend shows `detail`, or the first field message. |
| Lists | Paginated like DRF: `{"count": 42, "next": url|null, "previous": url|null, "results": [...]}`. Query `?page=2`. |
| Access | **A firm user sees only its own firm's cases.** The backend enforces this; the frontend only hides menus. Staff (reviewer, admin) see all firms. **Before a case is `sent`, a firm user gets progress only:** the detail has empty `flags`, null `totals` and `stay`, a neutral `status_detail`; `/lines/`, `/report/` and the downloads answer `403`. |
| CORS | Allow the frontend origin, header `Authorization`, and expose `Content-Disposition` (for download file names). |

## Roles

| `role` | Who | Screens |
|---|---|---|
| `firm` | Law firm user | Upload a bill, My reports |
| `reviewer` | MeshKor reviewer | Cases, Upload, Review, Report & send, Data sources, Audit log |
| `admin` | MeshKor admin | Same as reviewer |

## 1. Auth

### `POST /api/auth/login/`
Request `{"email": "a@firm.com", "password": "…"}`
Response `200`:
```json
{
  "access": "<jwt>",
  "refresh": "<jwt>",
  "user": {"id": 7, "name": "Jane Doe", "email": "a@firm.com", "role": "firm",
           "firm": {"id": 3, "name": "Smith & Lee LLP"}}
}
```
`firm` is `null` for staff. Wrong password → `401 {"detail": "Wrong email or password."}`.

### `POST /api/auth/refresh/`
Request `{"refresh": "<jwt>"}` → `200 {"access": "<jwt>"}` (a new `refresh` may also be returned).

### `GET /api/auth/me/`
→ `200` the `user` object above.

### `POST /api/auth/logout/`
Request `{"refresh": "<jwt>"}` → `204`. (Blacklist the refresh token.)

## 2. Cases

### Case statuses (`status`)

| Value | Meaning | Shown to firm as |
|---|---|---|
| `uploaded` | Files received | In progress |
| `processing` | Being read, matched and priced | In progress |
| `needs_review` | Ready for a reviewer | In progress |
| `returned` | Reviewer sent it back for another pass | In progress |
| `no_price_file` | No hospital price file found for the date of service | In progress |
| `error` | Processing failed (see `status_detail`) | In progress |
| `sent` | Approved and released to the firm | Ready |

### Case summary object
```json
{
  "id": 101,
  "case_number": "MK-2026-0101",
  "firm": {"id": 3, "name": "Smith & Lee LLP"},
  "matter_ref": "SL-2026-0142",
  "visit_summary": "ER visit, head and neck CT",
  "hospital_name": "Ohio State University Hospitals",
  "ccn": "360085",
  "setting": "outpatient",
  "service_date_from": "2026-08-14",
  "service_date_to": "2026-08-14",
  "payer_name": "Anthem",
  "billed_total": 9647.87,
  "status": "needs_review",
  "status_detail": null,
  "created_at": "2026-10-23T09:20:11+05:30",
  "sent_at": null
}
```
`setting` is `outpatient` or `inpatient`. `visit_summary`, `hospital_name`, `ccn`, `payer_name`, `billed_total` may be `null` until processing has run.

### `GET /api/cases/`
Query: `status` (one value or comma list), `search` (case number, matter ref, hospital, payer), `firm` (staff only), `page`.
→ paginated case summaries, newest first.

### `GET /api/cases/stats/` (staff)
```json
{"needs_review": 3, "processing": 2, "sent_this_month": 2, "billed_open_total": 86342.15}
```

### `POST /api/cases/` (multipart/form-data)
Fields: `matter_ref` (text), `report_for` (`plaintiff` | `defense` | `lien_resolution`), `consent` (`true`, required), `bill` (file, required, PDF/JPG/PNG/TIFF ≤ 50 MB), `eob` (file, optional).
Staff may also send `firm_id`. → `201` case summary (status `uploaded`). The answer comes at once; the pricing runs in the background (`uploaded` → `processing` → `needs_review`, `no_price_file` or `error`). Poll `GET /api/cases/{id}/` (the website does every 3 s) until the status leaves `uploaded`/`processing`.

### `GET /api/cases/{id}/` (case detail)
Case summary plus:
```json
{
  "report_for": "plaintiff",
  "bill_type": "UB-04",
  "files": [
    {"kind": "bill", "name": "bill.pdf", "size_bytes": 36211, "sha256": "7c41e0…", "uploaded_at": "…"},
    {"kind": "eob",  "name": "eob.pdf",  "size_bytes": 20110, "sha256": "…",      "uploaded_at": "…"}
  ],
  "hospital_match": {
    "npi": "1234567890",
    "ccn": "360085",
    "hospital_name": "Ohio State University Hospitals",
    "price_file": {
      "file_name": "31-1340739_OHIO-STATE-UNIVERSITY-HOSPITALS_standardcharges.csv",
      "period": "2026-10",
      "last_updated_on": "2026-07-01",
      "covers_service_date": true
    }
  },
  "totals": {"billed": 9647.87, "payer_rate": 3114.60, "median": 2964.90,
             "cash": null, "medicare": 1400.43, "cost": 2026.05,
             "payer_rate_is_estimate": false,
             "basis": "service_date",        /* or "estimate": no price file covers the service date, values come from the nearest file */
             "coverage": {"payer_rate": 61, "payer_rate_billed": 5921.0, "median": 61, "median_billed": 5921.0, "cash": 0, "cash_billed": 0,
                          "medicare": 100, "medicare_billed": 9647.87, "cost": 100, "cost_billed": 9647.87,
                          "lines": 11, "lines_with": {"payer_rate": 4, "median": 4, "cash": 0, "medicare": 11, "cost": 11}}},
  /* coverage: the billed dollars (and % of the bill) on the lines that have each value; absent for an inpatient stay */
  "flags": [
    {"id": 55, "kind": "low_confidence", "severity": "check", "line_no": 5,
     "title": "Line 5 · 36415 read with 71 % certainty",
     "detail": "Check the code and charge against the bill image.", "resolved": false},
    {"id": 56, "kind": "packaged", "severity": "info", "line_no": null,
     "title": "4 lines have no separate Medicare payment",
     "detail": "Lines 5, 9, 10, 11 are packaged into other payments.", "resolved": false}
  ],
  "stay": null,
  "eob": null   /* when an EOB was read: {"payer": "Anthem Blue Cross and Blue Shield", "plan": "…", "payer_group": "Anthem",
                   "claim_number": "…", "provider": "…", "date_from": "2026-08-14", "date_to": "2026-08-14", "ms_drg": null,
                   "level": "line" | "stay", "columns": ["billed", "allowed", …], "method": "text" | "ocr" | "docx",
                   "totals": {"billed": 9647.87, "discount": null, "allowed": 3501.80, "not_covered": null, "deductible": 500.0,
                              "copay": 0.0, "coinsurance": 600.36, "paid": 2401.44, "patient": 1100.36},
                   "lines": 11, "lines_matched": 11, "bill_lines": 11,
                   "vs_price_file": {"allowed": 2382.0, "posted": 2472.36, "pct": -4},   (same lines; may be missing)
                   "file_name": "…", "sha256": "…"} */
}
```
`eob` is `null` when no EOB was uploaded or it could not be read (then a flag of kind `eob` says why). Flag kinds include `eob`.
`hospital_match` is `null` when no match was found. `totals.cash` is `null` when the hospital posts no cash price.

Flag `kind` values: `low_confidence`, `no_rate`, `no_price_file`, `estimate`, `packaged`, `no_eob`, `drg_check`, `other`. `severity`: `check` (reviewer must act) or `info`.

For an inpatient case, `stay` is:
```json
{
  "ms_drg": "481",
  "drg_title": "Hip and femur procedures except major joint with CC",
  "drg_source": "bill",
  "drg_confirmed": false,
  "los_days": 3,
  "diagnoses": [{"code": "S72.301A", "description": "Fracture of shaft of right femur", "level": "principal"},
                {"code": "D62", "description": "Acute posthemorrhagic anemia", "level": "cc"}],
  "values": {"billed": 58612.00, "payer_rate": 38520.00, "median": 36900.00,
             "medicare": 21740.00, "cost": 12308.52}
}
```
`drg_source`: `bill`, `grouper`, or `reviewer` (a reviewer typed a different DRG in confirm). `level`: `principal`, `mcc`, `cc` or `other` (from the CMS MS-DRG CC/MCC list on the date of service); `description` is the CMS name of the code.

### `GET /api/cases/{id}/lines/?basis=service_date|estimate`
`service_date` (default) = rates in force on the date of service. `estimate` = hospital's current payer ÷ Medicare ratio × Medicare on the date of service.
→ array (not paginated):
```json
[{
  "line_no": 1, "service_date": "2026-08-14", "revenue_code": "0450", "hcpcs": "99285",
  "modifiers": "", "units": 1, "description": "HC EMERGENCY ROOM LEVEL 5",
  "charge": 3403.00, "confidence": 0.98,
  "payer_rate": 1452.00, "payer_rate_is_estimate": false,
  "median": 1388.00, "p10": 1120.00, "p90": 1690.00, "cash": null,
  "medicare": 598.40, "medicare_status": "priced", "medicare_source": "OPPS 2026Q3, wage-adjusted",
  "cost": 714.63,
  "eob_allowed": 1450.00, "eob_paid": 760.00, "eob_patient": 690.00,   /* null when the line is not on the EOB */
  "status": "priced",
  "sources": [{"label": "Hospital price file", "file_name": "31-1340739_…csv", "sha256": "…"}]
}]
```
`medicare_status`: `priced`, `packaged`, `none`. Line `status`: `priced`, `packaged`, `unpriced_no_code`, `unpriced_no_hospital_row`. Any benchmark may be `null`.

### `POST /api/cases/{id}/flags/{flag_id}/resolve/` (staff)
Request `{"note": "optional"}` → `200` the flag with `"resolved": true`.

### `POST /api/cases/{id}/drg/confirm/` (staff)
Request `{"ms_drg": "481"}` → `200` the `stay` object with `"drg_confirmed": true`.

## 3. Report and release

### `GET /api/cases/{id}/report/`
The report as data, for the on-screen preview (the PDF is built from the same data):
```json
{
  "title": "Reasonable value of hospital charges",
  "generated_at": "2026-10-23T09:41:00+05:30",
  "summary": [
    {"key": "billed",     "benchmark": "Billed charges",                    "total": 9647.87, "pct_of_billed": 100, "coverage_pct": 100, "note": ""},
    {"key": "eob_allowed", "benchmark": "Allowed by Anthem … for this claim (EOB)", "total": 3501.80, "pct_of_billed": 36, "coverage_pct": 100, "note": "…"},   /* only with an EOB */
    {"key": "eob_paid",   "benchmark": "Paid by Anthem … (EOB)",            "total": 2401.44, "pct_of_billed": 25,  "coverage_pct": 100, "note": "plus the patient's share …"},
    {"key": "payer_rate", "benchmark": "Hospital's own rate with Anthem",   "total": 2472.36, "pct_of_billed": 42,  "coverage_pct": 61,
                          "note": "4 of 11 lines, 61 % of billed charges; the % compares those lines only"},
    {"key": "median",     "benchmark": "Median of the hospital's commercial insurer rates", "total": 2396.76, "pct_of_billed": 40,  "coverage_pct": 61, "note": "…"},
    {"key": "cash",       "benchmark": "Hospital's cash price",             "total": 15.00,   "pct_of_billed": null, "coverage_pct": 1,
                          "note": "posted on only 1 of 11 lines (1 % of billed charges): not comparable with the bill"},
    {"key": "cost",       "benchmark": "Hospital's cost (cost report)",     "total": 2026.05, "pct_of_billed": 21,  "coverage_pct": 100, "note": ""},
    {"key": "medicare",   "benchmark": "Medicare rate for this hospital",   "total": 1077.80, "pct_of_billed": 11,  "coverage_pct": 100, "note": ""}
  ],
  "summary_text": "The hospital billed $9,647.87. …",
  "stay": null,   /* inpatient: {"ms_drg": "481", "drg_title": "…", "drg_source": "bill", "drg_confirmed": false, "los_days": 3,
                     "medicare_source": "IPPS FY2026 …", "payer_rate_is_estimate": false, "p10": 22400.0, "p90": 25600.0} */
  "eob": null,   /* or the case's eob object without file_name, sha256, columns and method */
  "lines": [ /* same objects as GET /lines/ */ ],
  "sources": [{"data": "Hospital price file", "file_name": "…", "dated": "2026-07-01", "sha256": "…"}],
  "method": "Each billed line is matched …",
  "limits": "Percentile amounts exist only for …",
  "reviewer": {"name": "…", "approved_at": null}
}
```
`pct_of_billed` always compares the total with the billed charges of the **same lines**: when a benchmark has a value on only some lines (`coverage_pct` < 100), the % uses those lines' charges, and `note` says so. A benchmark on fewer than half of the billed charges has `pct_of_billed: null`. The cash row is present only when the hospital posts a cash price. For a self-pay bill the payer row is titled "No insurer on the bill".

### Downloads (file responses, auth required)
| Endpoint | Content-Type | File name (Content-Disposition) |
|---|---|---|
| `GET /api/cases/{id}/report.pdf` | `application/pdf` | `MK-2026-0101_valuation_report.pdf` |
| `GET /api/cases/{id}/report.csv` | `text/csv` | `MK-2026-0101_data_appendix.csv` |

Firm users may download only when the case `status` is `sent`. Staff may download any time (draft watermark is up to the backend).

### `POST /api/cases/{id}/approve/` (staff)
Request `{"note": "optional"}` → `200` case summary with `status: "sent"`. The backend emails the firm, writes the audit log, and blocks approval by the same user who resolved the flags only if that rule is turned on.

### `POST /api/cases/{id}/return/` (staff)
Request `{"note": "required reason"}` → `200` case summary with `status: "returned"`.

### `POST /api/cases/{id}/feedback/` (firm, after `sent`)
Request `{"outcome": "reduced" | "partly" | "no_change", "price_per_report": 250, "pricing_model": "per_report" | "subscription", "comment": "…"}` → `201`.

## 4. Firms (staff)

### `GET /api/firms/`
→ `[{"id": 3, "name": "Smith & Lee LLP"}]` (a plain list or a paginated list; both work). Used for the firm picker when staff upload a bill.

## 5. Data sources (staff)

### `GET /api/data-sources/`
```json
{
  "verify": {"pass": 245, "fail": 0, "run_at": "2026-10-22T23:39:00+05:30"},
  "reference": [{"name": "Medicare outpatient (OPPS)", "rows": 224012, "covers": "2024Q1–2026Q4", "status": "ok"}],
  "price_files": [{"ccn": "360085", "hospital_name": "Ohio State University Hospitals",
                   "last_updated_on": "2026-07-01", "rows": 2366510, "status": "loaded"}]
}
```
Reference `status`: `ok`, `partial`, `missing`. Price file `status`: `loaded`, `downloading`, `not_found`, `error`.

## 6. Audit log (staff)

### `GET /api/audit/?case={id}&page=`
→ paginated `{"at": "…", "actor": "Jane Doe (Smith & Lee LLP)", "action": "Bill uploaded", "detail": "bill.pdf · consent recorded", "case_number": "MK-2026-0101"}`, newest first.

## 6b. Admin (role `admin` only; everyone else gets `403`)

### Firms
- `GET /api/admin/firms/` → `[{"id", "name", "contact_email", "active", "created_at", "users", "cases", "open_cases"}]`
- `POST /api/admin/firms/` `{"name", "contact_email"?}` → `201` firm. A name in use (any case) → `400`.
- `PATCH /api/admin/firms/{id}/` `{"name"?, "contact_email"?, "active"?}` → firm. `active: false`: its users cannot sign in (`403` "Your firm's portal account is turned off"), it leaves `GET /api/firms/`, and its users are signed out.

### Users
- `GET /api/admin/users/?role=&firm=` → `[user object + {"first_name", "last_name", "active", "last_login", "date_joined"}]`
- `POST /api/admin/users/` `{"email", "name"?, "role", "firm_id"?}` → `201` user plus `"temporary_password"` (shown once). A firm user needs `firm_id`; staff get no firm.
- `PATCH /api/admin/users/{id}/` `{"email"?, "name"?, "role"?, "firm_id"?, "active"?}` → user. `400` for: your own role or account, the last active admin, a firm user without a firm, an email in use.
- `POST /api/admin/users/{id}/reset-password/` → `{"temporary_password"}`; the user is signed out everywhere.

The `user` object (login, `/api/auth/me/`) has `"must_change_password": true` after an add or a reset; the website then shows only **Choose your own password**.

### Own password (every user)
- `POST /api/auth/password/` `{"current_password", "new_password"}` → user object, `must_change_password: false`. `400` with `new_password: [...]` when Django's password rules refuse it.

### Payer names
- `GET /api/admin/payer-names/` → `{"groups": [...], "names": [{"id", "name", "group", "created_at", "created_by"}], "unknown": [{"payer_name", "cases", "open"}]}`
- `POST /api/admin/payer-names/` `{"name", "group"}` → `201` `{"id", "name", "group", "open_cases"}`. `group` must be one of `groups`.
- `DELETE /api/admin/payer-names/{id}/` → `204`
- `POST /api/admin/payer-names/reprice/` `{"name"}` → `{"repriced": [{"id", "case_number", "status", "payer_group"}]}`: open cases (not sent, at most 25) with this insurer name, priced again now; a reviewer's DRG is kept.

## 7. Checklist for the backend

1. All endpoints above, with the same paths, keys and enums.
2. Firm isolation on every case endpoint (`404` for another firm's case).
3. CORS + `Content-Disposition` exposed.
4. Bills and EOBs stored encrypted, outside the repo; every view and download written to the audit log.
5. `401` on an expired token (not `403`), so the frontend refreshes.
