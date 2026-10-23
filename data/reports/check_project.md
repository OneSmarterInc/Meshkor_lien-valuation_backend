# MeshKor: project data check  (2026-10-23 00:00)
Raw folder: E:\Hansavahini\Datasetof CMS   exists: True

## 1. Parquet tables
| Status | For | Data | Rows | Detail |
|---|---|---|---|---|
| OK | Both | Providers (NPPES) | 9,852,180 | 197 file(s) |
| OK | Both | CCN-NPI links | 25,444 | 1 file(s) |
| OK | Lien | Physician fees (MPFS) | 24,809,708 | 12 file(s) |
| OK | Lien | Outpatient (OPPS) | 224,012 | 1 file(s) |
| OK | Lien | Surgery center (ASC) | 82,116 | 1 file(s) |
| OK | Lien | Inpatient DRG weights | 2,313 | 1 file(s) |
| OK | Lien | Inpatient hospital factors | 9,330 | 1 file(s) |
| OK | Lien | Cost reports (cost-to-charge) | 16,049 | 1 file(s) |
| OK | Lien | Lab fees (CLFS) | 25,340 | 1 file(s) |
| OK | Lien | Equipment fees (DMEPOS) | 2,224,675 | 1 file(s) |
| OK | Lien | Ambulance fees | 3,924 | 1 file(s) |
| OK | Lien | Anesthesia conversion factors | 1,308 | 1 file(s) |
| OK | Lien | Anesthesia base units | 276 | 1 file(s) |
| OK | Lien | Zip to locality | 171,821 | 1 file(s) |
| OK | Lien | Coding edits (NCCI) | 4,506,527 | 1 file(s) |
| OK | Lien | Unit limits (MUE) | 357,057 | 1 file(s) |
| OK | Both | Drug payment limits (ASP) | 10,795 | 12 of 12 quarters |
| OK | Both | NDC to HCPCS crosswalk | 95,545 | 12 of 12 quarters |
| OK | Both | HCPCS code names | 104,844 | 12 of 12 quarters |
| OK | Drug | NADAC drug costs | 1,001,844 | 1 file(s) |
| OK | Drug | FDA NDC products | 116,501 | 1 file(s) |
| OK | Drug | FDA NDC packages | 219,045 | 1 file(s) |
| MISSING | Drug | 340B entities | - | no Parquet file |
| MISSING | Drug | 340B contract pharmacies | - | no Parquet file |
| OK | Lien | MS-DRG list (titles) | 5,390 | 7 file(s) |
| OK | Lien | MS-DRG diagnosis map | 618,768 | 7 file(s) |

## 2. Hospital price files (ref_hospital_mrf)
| Status | CCN | Hospital | Period | Rows | Last updated |
|---|---|---|---|---|---|
| OK | 360085 | Ohio State University Hospitals | 2026-10 | 2,366,510 | 2026-07-01 |
| OK | 360242 | James Cancer Hospital | 2026-10 | 4,470,209 | 2026-07-01 |
| MISSING | 360051 | Miami Valley Hospital | - | - | - |
| MISSING | 360180 | Cleveland Clinic Main Campus | - | - | - |

## 3. Downloaded but not loaded (raw folders)
| Folder | Files | Note |
|---|---|---|
| MSDRG | 77 | tables loaded by load_msdrg.py; the Java grouper is used later |
| PARTB_SPEND | 2 | Part B spending by drug; loader not written |
| IDR | 29 | loader not written |
| MEDICAID_OH | 4 | loader not written |
| BWC_OH | 4 | loader not written |

## 4. Not available yet (no action in this check)
| Item | Why |
|---|---|
| Real pilot bills + EOBs | come from the 3 law firms |
| Price files 2024-2025 history | Wayback search / hospital request |
| Price files of the pilot-bill hospitals | known after the bills arrive |
| NUBC revenue codes | paid license |
| HUD ZIP crosswalk 2026 Q3 | not published yet |

## 5. Last verify reports
- verify_latest.md (2026-10-22 23:39): **245 pass · 0 fail · 0 not run · 23 info**
- check_downloads.txt (2026-10-22 23:39): === RESULT: 0 FAIL ===
- verify_msdrg.md (2026-10-22 23:16): | V44: DRG 291 title | PASS | Heart Failure and Shock with MCC |
- verify_mrf_360085_2026-10.md (2026-10-22 16:35): Run: 2026-10-22T16:35:13  Result: **15 pass, 0 fail**
- verify_mrf_360242_2026-10.md (2026-10-22 16:52): Run: 2026-10-22T16:52:38  Result: **15 pass, 0 fail**

## RESULT: 4 item(s) missing or incomplete
