# MeshKor Step 1 — verification report

Created 2026-10-22T18:09:14+00:00 · Python 3.10.10 · DuckDB 1.5.6

**245 pass · 0 fail · 0 not run · 23 info**


## §8.1

| Status | Check | Detail |
|---|---|---|
| PASS | table 1 ref_provider | 9,852,180 rows; dates 2005-05-23 → 9999-12-31; 1 source hash(es) |
| PASS | table 2 ref_mpfs | 24,809,708 rows; dates 2024-01-01 → 2026-12-31; 12 source hash(es) |
| PASS | table 3 ref_opps | 224,012 rows; dates 2024-01-01 → 2026-12-31; 12 source hash(es) |
| PASS | table 4 ref_ipps_drg | 2,313 rows; dates 2024-10-01 → 2027-09-30; 3 source hash(es) |
| PASS | table 4 ref_ipps_hospital | 9,330 rows; dates 2024-10-01 → 2027-09-30; 3 source hash(es) |
| PASS | table 5 ref_asc | 82,116 rows; dates 2024-01-01 → 2026-12-31; 24 source hash(es) |
| PASS | table 6 ref_ncci_ptp | 4,506,527 rows; dates 1995-12-31 → 9999-12-31; 8 source hash(es) |
| PASS | table 6 ref_mue | 357,057 rows; dates 2024-01-01 → 2026-12-31; 24 source hash(es) |
| PASS | table 7 ref_hcris | 16,049 rows; dates 2022-10-01 → 2026-06-30; 4 source hash(es) |
| PASS | table 8 ref_ccn_npi | 25,444 rows; dates 2026-07-31 → 9999-12-31; 4 source hash(es) |
| PASS | table 9 ref_code_specialty | 167,634 rows; dates 2024-01-01 → 9999-12-31; 1 source hash(es) |
| PASS | table 10 ref_asp | 10,795 rows; dates 2024-01-01 → 2026-12-31; 20 source hash(es) |
| PASS | table 10 ref_ndc_hcpcs | 95,545 rows; dates 2024-01-01 → 2026-12-31; 49 source hash(es) |
| PASS | table 10 ref_hcpcs_code | 104,844 rows; dates 2024-01-01 → 2026-12-31; 12 source hash(es) |
| PASS | table 11 ref_clfs | 25,340 rows; dates 2024-01-01 → 2026-12-31; 12 source hash(es) |
| PASS | table 12 ref_dmepos | 2,224,675 rows; dates 2024-01-01 → 2026-12-31; 12 source hash(es) |
| PASS | table 12 ref_dmepos_rural_zip | 191,052 rows; dates 2024-01-01 → 2026-12-31; 12 source hash(es) |
| PASS | table 13 ref_ambulance | 3,924 rows; dates 2024-01-01 → 2026-12-31; 3 source hash(es) |
| PASS | table 13 ref_zip_locality | 171,821 rows; dates 2024-01-01 → 2026-12-31; 3 source hash(es) |
| PASS | table 14 ref_anesthesia_cf | 1,308 rows; dates 2024-01-01 → 2026-12-31; 4 source hash(es) |
| PASS | table 14 ref_anesthesia_base_units | 276 rows; dates 2022-01-01 → 9999-12-31; 1 source hash(es) |

## §11

| Status | Check | Detail |
|---|---|---|
| PASS | table 17 ref_geo | 1,021,553 rows; dates 2024-01-01 → 2026-06-30; 20 source hash(es) |
| PASS | table 17 ref_geo_zcta_county | 46,960 rows; dates 2020-01-01 → 9999-12-31; 1 source hash(es) |
| PASS | table 19 ref_quality_hospital | 5,419 rows; dates 2026-09-30 → 9999-12-31; 1 source hash(es) |
| PASS | table 19 ref_quality_measure | 473,384 rows; dates 2026-09-30 → 9999-12-31; 4 source hash(es) |
| PASS | table 19 ref_quality_asc | 68,532 rows; dates 2026-09-30 → 9999-12-31; 1 source hash(es) |
| PASS | table 20 ref_ownership | 171,103 rows; dates 2026-09-29 → 9999-12-31; 2 source hash(es) |
| PASS | table 20 ref_chow | 779 rows; dates 2026-09-29 → 9999-12-31; 1 source hash(es) |
| PASS | table 20 ref_chow_npi | 479 rows; dates 2026-09-29 → 9999-12-31; 1 source hash(es) |
| PASS | table 21 ref_nadac | 1,001,844 rows; dates 2022-11-23 → 9999-12-31; 3 source hash(es) |
| PASS | table 21 ref_ndc_product | 116,501 rows; dates 2026-10-21 → 9999-12-31; 1 source hash(es) |
| PASS | table 21 ref_ndc_package | 219,045 rows; dates 2026-10-21 → 9999-12-31; 1 source hash(es) |

## §3.2

| Status | Check | Detail |
|---|---|---|
| PASS | raw file unchanged: AMBULANCE/2026 | 41658147eac5a162 |
| PASS | raw file unchanged: AMBULANCE/2025 | c1dbbdba39fe2eb2 |
| PASS | raw file unchanged: AMBULANCE/2024 | 41f8221a775cac3d |
| PASS | raw file unchanged: ANESTHESIA | 9bf71b437a1061b1 |
| PASS | raw file unchanged: MPFS2024D | 2604538d8f6b8265 |
| PASS | raw file unchanged: MPFS | 51afbeb853bce73c |
| PASS | raw file unchanged: MPFS2025 | 5f5c944453462828 |
| PASS | raw file unchanged: MPFS2024 | 6f333a2f554ee30c |
| PASS | raw file unchanged: MPFS2024B | b6ba19357dca0565 |
| PASS | raw file unchanged: MPFS2024A | 55c3fb57e2377f7b |
| PASS | raw file unchanged: MPFS2025A | 8bc4c67526656b78 |
| PASS | raw file unchanged: MPFS2025B | 1fff318c974812d9 |
| PASS | raw file unchanged: MPFS2025C | c50de068a8263312 |
| PASS | raw file unchanged: MPFS2026A | 6eacf966b1e740d9 |
| PASS | raw file unchanged: MPFS2026B | 8aea553288e44804 |
| PASS | raw file unchanged: MPFS2026C | c7fe4e5b4bbb9499 |
| PASS | raw file unchanged: ASC | af16cc05f7a46296 |
| PASS | raw file unchanged: ASC2025 | 265ebba2496d31ca |
| PASS | raw file unchanged: ASC2024 | 33b68627f4886baa |
| PASS | raw file unchanged: ASC2024A | 2608a7ca655217f9 |
| PASS | raw file unchanged: ASC2024B | 00b7a5125f6e40ff |
| PASS | raw file unchanged: ASC2024C | 8ac759d830f72cda |
| PASS | raw file unchanged: ASC2025A | 8c57e464f81c2091 |
| PASS | raw file unchanged: ASC2025B | 92c35a8b7e6211e8 |
| PASS | raw file unchanged: ASC2025C | f83806c69a3a35e1 |
| PASS | raw file unchanged: ASC2026A | 51f77275e93877a9 |
| PASS | raw file unchanged: ASC2026B | 74ccae7b4005208f |
| PASS | raw file unchanged: ASC2026C | 833cb837897eb290 |
| PASS | raw file unchanged: ASP/2024Q1 | 5e9560bc0a375755 |
| PASS | raw file unchanged: ASP/2024Q2 | 23480cb404ef36e4 |
| PASS | raw file unchanged: ASP/2024Q3 | 147d7640ffdc35e4 |
| PASS | raw file unchanged: ASP/2024Q4 | b3b8a01ee581954b |
| PASS | raw file unchanged: ASP/2025Q1 | 8f78af585136166c |
| PASS | raw file unchanged: ASP/2025Q2 | b64130c917a32f4a |
| PASS | raw file unchanged: ASP/2025Q3 | 2731498d1a69d0f5 |
| PASS | raw file unchanged: ASP/2025Q4 | 6fd67a403973d969 |
| PASS | raw file unchanged: ASP/2026Q1 | ee3a4b9a4a2690d7 |
| PASS | raw file unchanged: ASP/2026Q2 | faa5d054d262ddc3 |
| PASS | raw file unchanged: ASP/2026Q3 | a345acd5d3750d08 |
| PASS | raw file unchanged: ASP/2026Q4 | 0d1e10450c178612 |
| PASS | raw file unchanged: ENROLLMENTS | c09f7db4dfbc2e8a |
| PASS | raw file unchanged: OWNERSHIP/2026-10 | f60a1b48967dc9f4 |
| PASS | raw file unchanged: CLFS/2026Q4 | 36e3ee8769971686 |
| PASS | raw file unchanged: CLFS/2025Q4 | f133417147f4c942 |
| PASS | raw file unchanged: CLFS/2024Q4 | a95268fa972965ef |
| PASS | raw file unchanged: CLFS/2024Q1 | 180b90dff4386b2e |
| PASS | raw file unchanged: CLFS/2024Q2 | d178ce7cd501885b |
| PASS | raw file unchanged: CLFS/2024Q3 | c4d9c87d8edbcd8f |
| PASS | raw file unchanged: CLFS/2025Q1 | 3a6ae381501ee77a |
| PASS | raw file unchanged: CLFS/2025Q2 | 97b70c0d1b46d71c |
| PASS | raw file unchanged: CLFS/2025Q3 | 166efc2b2ddddf11 |
| PASS | raw file unchanged: CLFS/2026Q1 | 5be760b9fc8660c5 |
| PASS | raw file unchanged: CLFS/2026Q2 | 43c81064de5bf84a |
| PASS | raw file unchanged: CLFS/2026Q3 | 179e916d69121b89 |
| PASS | raw file unchanged: UTILIZATION | 0893456869f155e0 |
| PASS | raw file unchanged: DMEPOS/2026D | b87e69dda8d536c7 |
| PASS | raw file unchanged: DMEPOS/2025D | e0fbe6dcdb1c76ac |
| PASS | raw file unchanged: DMEPOS/2024D | bab7fd9782ea6604 |
| PASS | raw file unchanged: DMEPOS/2024A | a8c8018778cebb5e |
| PASS | raw file unchanged: DMEPOS/2024B | 52997b1ee2bf8e83 |
| PASS | raw file unchanged: DMEPOS/2024C | 77ee941845a5a23a |
| PASS | raw file unchanged: DMEPOS/2025A | 9c9d9d0584b1ee9c |
| PASS | raw file unchanged: DMEPOS/2025B | 33454976cd03f9cd |
| PASS | raw file unchanged: DMEPOS/2025C | 8005fbc76747ae80 |
| PASS | raw file unchanged: DMEPOS/2026A | ba175cc113bf2a57 |
| PASS | raw file unchanged: DMEPOS/2026B | 5b65b9f15a0c6f55 |
| PASS | raw file unchanged: DMEPOS/2026C | d367d30b6d036dfe |
| PASS | raw file unchanged: HUD/2024Q1 | 608fbacc8bf83098 |
| PASS | raw file unchanged: HUD/2024Q2 | 38a7348936adfd2a |
| PASS | raw file unchanged: HUD/2024Q3 | d14e1d3267175dec |
| PASS | raw file unchanged: HUD/2024Q4 | 7dc6254b77ed582f |
| PASS | raw file unchanged: HUD/2025Q1 | bf49ecf00d902cdc |
| PASS | raw file unchanged: HUD/2025Q2 | badf8809ada85670 |
| PASS | raw file unchanged: HUD/2025Q3 | 578c2c160fd8da3c |
| PASS | raw file unchanged: HUD/2025Q4 | add03ab8c2767ecc |
| PASS | raw file unchanged: HUD/2026Q1 | 95f54243886cc5ba |
| PASS | raw file unchanged: HUD/2026Q2 | 8554296b3a708d29 |
| PASS | raw file unchanged: CENSUS/ZCTA2020 | 62d92d379a4c3349 |
| PASS | raw file unchanged: HCPCS/2024Q1 | a038387f62f59851 |
| PASS | raw file unchanged: HCPCS/2024Q2 | 109489d49a2408d3 |
| PASS | raw file unchanged: HCPCS/2024Q3 | fc150c855ea16359 |
| PASS | raw file unchanged: HCPCS/2024Q4 | 2ffbc24cd15395dc |
| PASS | raw file unchanged: HCPCS/2025Q1 | e934df67bb951772 |
| PASS | raw file unchanged: HCPCS/2025Q2 | bdd84807958b35f6 |
| PASS | raw file unchanged: HCPCS/2025Q3 | 90d5ea712e11cba3 |
| PASS | raw file unchanged: HCPCS/2025Q4 | 8f80b5b076ea09c2 |
| PASS | raw file unchanged: HCPCS/2026Q1 | d7e3a387555f5c05 |
| PASS | raw file unchanged: HCPCS/2026Q2 | d8f2b2dd1295a10b |
| PASS | raw file unchanged: HCPCS/2026Q3 | 0a7a74609cb9970a |
| PASS | raw file unchanged: HCPCS/2026Q4 | e526da8e8616ecc0 |
| PASS | raw file unchanged: HCRIS/HOSP10FY2023 | c66a0f1683596338 |
| PASS | raw file unchanged: HCRIS/HOSP10FY2024 | f288f704f227c0b2 |
| PASS | raw file unchanged: HCRIS/HOSP10FY2025 | 5aca20a2c5d3f540 |
| PASS | raw file unchanged: HCRIS/HOSP10FY2026 | de7fbd886285fe67 |
| PASS | raw file unchanged: IPPS/FY2027/cms-1849-fr-and-cn-table-5.zip | 3b43654767907b1c |
| PASS | raw file unchanged: IPPS/FY2026/cms-1833-f-table-5.zip | 14dba6b8f06ab819 |
| PASS | raw file unchanged: IPPS/FY2025/fy2025-ipps-final-rule-and-correction-notice-table-5.zip | d5e0a0bd231412e1 |
| PASS | raw file unchanged: IPPS/FY2027/fy-2027-ipps-fr-cn-impact-file.zip | 6e51b1015b6c5c93 |
| PASS | raw file unchanged: IPPS/FY2026/fy_2026_ipps_final_rule_impact_file.zip | c19ae04778a7018f |
| PASS | raw file unchanged: IPPS/FY2025/fy_2025_ipps_impact_file-fr-cn-ifc.zip | 1b650a7f96eef459 |
| PASS | raw file unchanged: NCCI/facilityoutpatienthospitalservicesmuetable-effective-10-01-2026 | f174b39ddcaf08fe |
| PASS | raw file unchanged: NCCI/practitionerservicesmuetable-effective-10-01-2026 | e165bcd1e39ee0db |
| PASS | raw file unchanged: MUE2025/hospital | 5a6593e69c8fba7b |
| PASS | raw file unchanged: MUE2025/practitioner | 90acec749e1f03f5 |
| PASS | raw file unchanged: MUE2024/hospital | 58da99490a301a85 |
| PASS | raw file unchanged: MUE2024/practitioner | 4205f956af329093 |
| PASS | raw file unchanged: MUE2024A/hospital | 76d6075fc988e138 |
| PASS | raw file unchanged: MUE2024A/practitioner | 2d670114795fa732 |
| PASS | raw file unchanged: MUE2024B/hospital | 19b60926d0e1d6ec |
| PASS | raw file unchanged: MUE2024B/practitioner | 4478e01e6208ca8b |
| PASS | raw file unchanged: MUE2024C/hospital | 65098cb1292d498f |
| PASS | raw file unchanged: MUE2024C/practitioner | 06b9378e968b349c |
| PASS | raw file unchanged: MUE2025A/hospital | aafdacf073fd63e9 |
| PASS | raw file unchanged: MUE2025A/practitioner | 86ce15fce2cd42ec |
| PASS | raw file unchanged: MUE2025B/hospital | 3097c3df389807f3 |
| PASS | raw file unchanged: MUE2025B/practitioner | fb97746498c8166c |
| PASS | raw file unchanged: MUE2025C/hospital | 35ae92a8e89f9ad0 |
| PASS | raw file unchanged: MUE2025C/practitioner | 1679c026f8a8cbec |
| PASS | raw file unchanged: MUE2026A/hospital | 0ffee7f6d05a694c |
| PASS | raw file unchanged: MUE2026A/practitioner | 96543e747e763d72 |
| PASS | raw file unchanged: MUE2026B/hospital | 79a93446622b2582 |
| PASS | raw file unchanged: MUE2026B/practitioner | 2e504c35d76c301c |
| PASS | raw file unchanged: MUE2026C/hospital | 49a57f35234feeea |
| PASS | raw file unchanged: MUE2026C/practitioner | c3ae164122f0f901 |
| PASS | raw file unchanged: NADAC/2024 | 272d312694c015c6 |
| PASS | raw file unchanged: NADAC/2025 | 8c5b1ca7ccf0118c |
| PASS | raw file unchanged: NADAC/2026 | 0845572e512132ee |
| PASS | raw file unchanged: NCCI/PTP/ccioph-v323r0-f1.zip | fdf7651190e17f60 |
| PASS | raw file unchanged: NCCI/PTP/ccioph-v323r0-f2.zip | 5f39fb6295824ad7 |
| PASS | raw file unchanged: NCCI/PTP/ccioph-v323r0-f3.zip | e323c7c723c9a8ba |
| PASS | raw file unchanged: NCCI/PTP/ccioph-v323r0-f4.zip | 0e731c4c0f5a2150 |
| PASS | raw file unchanged: NCCI/PTP/ccipra-v323r0-f1.zip | 40adc15de0b5cf94 |
| PASS | raw file unchanged: NCCI/PTP/ccipra-v323r0-f2.zip | e0c916cc5b0bf1b7 |
| PASS | raw file unchanged: NCCI/PTP/ccipra-v323r0-f3.zip | 79024324e5f2ac96 |
| PASS | raw file unchanged: NCCI/PTP/ccipra-v323r0-f4.zip | 028a6d91e27ab177 |
| PASS | raw file unchanged: FDA_NDC/2026-10 | 0bbf87f08dcc2b15 |
| PASS | raw file unchanged: OPPS | 0b2483f46bd2fe93 |
| PASS | raw file unchanged: OPPS2025 | c044636bbb871017 |
| PASS | raw file unchanged: OPPS2024 | a5500da0c2ce1066 |
| PASS | raw file unchanged: OPPS2024A | cd0094a6114f2d05 |
| PASS | raw file unchanged: OPPS2024B | 4175fce3d363bd24 |
| PASS | raw file unchanged: OPPS2024C | 0f51593ebf1f2f07 |
| PASS | raw file unchanged: OPPS2025A | 5f7ed650a467ce9e |
| PASS | raw file unchanged: OPPS2025B | 033b02a032543976 |
| PASS | raw file unchanged: OPPS2025C | 296e0e00061a0379 |
| PASS | raw file unchanged: OPPS2026A | 7a15f0ecd0280cd3 |
| PASS | raw file unchanged: OPPS2026B | 25b666a7023c190b |
| PASS | raw file unchanged: OPPS2026C | 8dc631d3dce30ee3 |
| PASS | raw file unchanged: NPES | b22e2fac1cef4575 |
| PASS | raw file unchanged: NPES/NPPES Deactivated NPI Report 20261012.xlsx | 0552b3192932726c |
| PASS | raw file unchanged: CARECOMPARE/2026-10 | 2aac9fdd370d8166 |
| PASS | raw file unchanged: ZIPLOC/2026 | a2060fccf48a1bed |

## load

| Status | Check | Detail |
|---|---|---|
| INFO | ref_asc warning | 1 HCPCS codes appear in both AA and BB in 2024Q4 |
| INFO | ref_asc warning | 1 HCPCS codes appear in both AA and BB in 2024Q2 |
| INFO | ref_asc warning | 1 HCPCS codes appear in both AA and BB in 2024Q3 |
| INFO | ref_asc warning | 4 HCPCS codes appear in both AA and BB in 2025Q1 |
| INFO | ref_asc warning | 1 HCPCS codes appear in both AA and BB in 2026Q1 |
| INFO | ref_ccn_npi warning | 0 extra CCN–NPI pairs from NPPES other identifiers (not in Hospital Enrollments) |
| INFO | ref_ccn_npi warning | 13,533 extra pairs from NPPES hospital NPIs matched on zip + address/name or city + name (4,156 NPIs match 2+ CCNs at one address; all kept) |
| INFO | ref_ccn_npi warning | ccn_npi_manual.csv: 2 approved rows have a CCN that is not in Hospital Enrollments (kept) |
| INFO | ref_ccn_npi warning | 21 reviewed pairs added from config/ccn_npi_manual.csv |
| INFO | ref_code_specialty warning | 0.2% of services have an NPI not found in ref_provider (taxonomy empty) |
| INFO | ref_hcris warning | FY2023: 122 reports with cost-to-charge ratio outside 0.05–1.5 |
| INFO | ref_hcris warning | FY2024: 126 reports with cost-to-charge ratio outside 0.05–1.5 |
| INFO | ref_hcris warning | FY2025: 61 reports with cost-to-charge ratio outside 0.05–1.5 |
| INFO | ref_hcris warning | 166 hospital-years have 2+ reports for different periods (fiscal-year change or change of ownership); all kept |
| INFO | ref_ncci_ptp warning | 4 rows share a key with another row in the same release (kept; see deletion_date) |

## §8.2

| Status | Check | Detail |
|---|---|---|
| PASS | ref_provider counts reported | 9,852,180 NPIs; 357,925 deactivated; 0 without a primary flag; 410,030 in Ohio |

## §8.3

| Status | Check | Detail |
|---|---|---|
| PASS | 5-code profile in one query | 5 of 5 codes returned for 2026-10-01 |

## §8.4

| Status | Check | Detail |
|---|---|---|
| PASS | DRG 470 wage-adjusted IPPS payment at 3 Ohio hospitals | Cleveland Clinic $12,473.11; Miami Valley Hospital $12,717.32; Ohio State University Hospitals $12,762.16 |

## §8.5

| Status | Check | Detail |
|---|---|---|
| PASS | 99214 Ohio on 2024-06-15 returns the 2024 rate (Spec example) | 2024-06-15 → 123.01 (2024B); 2026-11-15 → 129.83 (2026D) |
| PASS | 99214 Ohio rate differs between loaded releases | 2024-08-15 → 123.01 (2024C); 2025-11-15 → 120.16 (2025D); 2026-11-15 → 129.83 (2026D) |
| PASS | date before every loaded release returns no rate | 2023-06-15 → 0 rows |

## §2

| Status | Check | Detail |
|---|---|---|
| PASS | ref_mpfs: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_opps: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_asc: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_mue: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_ipps_drg: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_ipps_hospital: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_clfs: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_dmepos: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_dmepos_rural_zip: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_ambulance: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_zip_locality: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |
| PASS | ref_anesthesia_cf: releases for 2024, 2025 and 2026 | years with a release: 2024, 2025, 2026 |

## T10

| Status | Check | Detail |
|---|---|---|
| PASS | ref_asp: 12 quarters 2024Q1-2026Q4 | 12 of 12 |
| PASS | ref_ndc_hcpcs: 12 quarters 2024Q1-2026Q4 | 12 of 12 |
| PASS | ASP rows per quarter 700-1,200 | 819-1,012 |
| PASS | ASP crosswalk rows per quarter 6,000-9,000 | 6,684-8,245 |
| PASS | HCPCS empty only on NOC rows | ref_asp 0, ref_ndc_hcpcs 0 |
| PASS | ref_asp: no duplicate keys | 0 duplicate keys |
| INFO | ref_ndc_hcpcs: duplicate rows in the CMS files (kept as published) | AWP 3 |
| INFO | 2026Q4 ASP codes with no crosswalk NDC (CMS prices some codes without NDCs) | 1 codes |
| PASS | golden: J9271 (pembrolizumab 1 mg) payment limit Oct 2026 = 62.253 | 62.253 |
| PASS | ref_hcpcs_code: 12 quarters 2024Q1-2026Q4 | 12 of 12 |
| PASS | ref_hcpcs_code: 1 row per code per quarter | 0 duplicates |

## §10

| Status | Check | Detail |
|---|---|---|
| PASS | ref_hcpcs_code: no CPT/CDT descriptions | 0 rows |

## T10

| Status | Check | Detail |
|---|---|---|
| INFO | 2026Q4 ASP codes found in the HCPCS file (CPT vaccine codes 90xxx are not in it) | 32 ASP codes not in the HCPCS Level II file |

## §8.6

| Status | Check | Detail |
|---|---|---|
| INFO | Ohio acute-care NPIs (282N00000X, not subparts) without a CCN, all NPPES records | 142 of 394 unmatched (36.0%) |
| PASS | Ohio acute-care hospital NPIs without a CCN (federal, not-a-hospital, stale NPPES records left out): target < 5 % | 1 of 253 unmatched (0.4%); by category: closed 6/6 unmatched; federal 20/20 unmatched; hospital 1/174 unmatched; not_acute 6/6 unmatched; not_hospital 28/42 unmatched; stale 81/146 unmatched |
| INFO | all Ohio 282N* hospital NPIs (incl. subparts) without a CCN | 187 of 570 unmatched (32.8%); list with categories in data/reports/ccn_npi_ohio_unmatched.csv |
| INFO | Ohio IPPS hospitals (CCN) with at least 1 NPI | 115 of 117 |
| INFO | CCN–NPI pairs by source | address_zip: 9,733 pairs, 3,896 CCNs, 6,193 NPIs; enrollment: 9,161 pairs, 9,161 CCNs, 8,706 NPIs; enrollment_additional: 2,729 pairs, 1,020 CCNs, 2,709 NPIs; manual: 21 pairs, 14 CCNs, 21 NPIs; name_city: 1,988 pairs, 705 CCNs, 1,167 NPIs; name_zip: 1,812 pairs, 916 CCNs, 1,204 NPIs |
| INFO | match suggestions for review | 1 unmatched hospital NPIs have a likely CCN; review data/reports/ccn_npi_ohio_suggestions.csv and copy approved rows to config/ccn_npi_manual.csv |
| PASS | spot check 27447: Orthopedic Surgery yes, Dermatology no | top: Orthopedic Surgery 55%, Physician Assistant 30%, Ambulatory Surgical Center 9%; 10 plausible specialties |
| PASS | spot check 29881: Orthopedic Surgery yes, Cardiology no | top: Ambulatory Surgical Center 60%, Orthopedic Surgery 35%, Sports Medicine 3%; 6 plausible specialties |
| PASS | spot check 45378: Gastroenterology yes, Dermatology no | top: Gastroenterology 58%, Ambulatory Surgical Center 29%, General Surgery 6%; 10 plausible specialties |
| PASS | spot check 66984: Ophthalmology yes, Dermatology no | top: Optometry 57%, Ophthalmology 26%, Ambulatory Surgical Center 17%; 7 plausible specialties |
| PASS | spot check 73721: Diagnostic Radiology yes, Psychiatry no | top: Diagnostic Radiology 79%, Independent Diagnostic Testing Facility (IDTF) 9%, Orthopedic Surgery 9%; 10 plausible specialties |
| PASS | spot check 93000: Cardiology yes, Ophthalmology no | top: Cardiology 52%, Internal Medicine 13%, Interventional Cardiology 10%; 10 plausible specialties |
| PASS | spot check 17000: Dermatology yes, Cardiology no | top: Dermatology 64%, Physician Assistant 23%, Nurse Practitioner 10%; 10 plausible specialties |
| PASS | spot check 90837: Licensed Clinical Social Worker yes, Orthopedic Surgery no | top: Licensed Clinical Social Worker 53%, Psychologist, Clinical 38%, Licensed Professional Counselor 3%; 10 plausible specialties |
| PASS | spot check 88305: Pathology yes, Psychiatry no | top: Pathology 61%, Clinical Laboratory 22%, Dermatology 13%; 10 plausible specialties |
| PASS | spot check 99214: Internal Medicine yes | top: Family Practice 15%, Internal Medicine 14%, Nurse Practitioner 14%; 21 plausible specialties |

## golden

| Status | Check | Detail |
|---|---|---|
| PASS | MPFS 99214 Ohio non-facility, Q4 2026 (hand calc: (1.92*1.000+2.00*0.913+0.14*1.008)*33.4009) | expected 129.83, got 129.83 |
| PASS | MPFS 99214 Ohio facility, Q4 2026 | expected 83.18, got 83.18 |
| PASS | MPFS 27447 non-facility is NA (null) | expected None, got None |
| PASS | ASC 29881 Oct 2026 (Addendum AA) | expected 1644.87, got 1644.87 |
| PASS | ASC 73721 Oct 2026 (Addendum BB) | expected 131.48, got 131.48 |
| PASS | Anesthesia CF Ohio Q4 2026 (non-QP) | expected 20.25, got 20.25 |
| PASS | OPPS 27447 national rate, Oct 2026 Addendum B (weight 143.4859 x CF ~91.415) | expected 13116.76, got 13116.76 |
| PASS | IPPS DRG 470 at Miami Valley Hospital (360051), FY2027: (4245.76*0.9182+2602.24)*1.9563 | expected 12717.32, got 12717.32 |
| PASS | CLFS 0001U national limit, Q4 2026 (PUF_CLFS_CY2026_Q4V1) | expected 720.0, got 720.0 |
| PASS | DMEPOS A4221 Ohio non-rural fee, Oct 2026 (DMEPOS_OCT) | expected 25.87, got 25.87 |
| PASS | DMEPOS A4221 Ohio rural fee, Oct 2026 | expected 29.07, got 29.07 |
| PASS | Ambulance A0427 (ALS emergency) urban, carrier 01112 locality 05, CY2026 | expected 709.75, got 709.75 |
| PASS | Anesthesia base units 00100 | expected 5, got 5 |
| PASS | MUE 27447 practitioner Q4 2026 | expected 1, got 1 |

## NCCI

| Status | Check | Detail |
|---|---|---|
| PASS | part ccioph-v323r0-f1 | 475,042 rows; CMS page says 475,042 |
| PASS | part ccioph-v323r0-f2 | 474,962 rows; CMS page says 474,962 |
| PASS | part ccioph-v323r0-f3 | 475,041 rows; CMS page says 475,041 |
| PASS | part ccioph-v323r0-f4 | 443,837 rows; CMS page says 443,837 |
| PASS | part ccipra-v323r0-f1 | 675,157 rows; CMS page says 675,157 |
| PASS | part ccipra-v323r0-f2 | 674,914 rows; CMS page says 674,914 |
| PASS | part ccipra-v323r0-f3 | 675,035 rows; CMS page says 675,035 |
| PASS | part ccipra-v323r0-f4 | 612,539 rows; CMS page says 612,539 |

## §8.3 code profile (Ohio, DOS 2026-10-01)

| hcpcs | mpfs_nonfacility | mpfs_facility | opps_si | opps_national | asc_pi | asc_rate | ncci_pairs |
|---|---|---|---|---|---|---|---|
| 27447 |  | 1126.77 | J1 | 13116.76 | J8 | 9393.16 | 615 |
| 29881 |  | 495.19 | J1 | 3342.87 | A2 | 1644.87 | 513 |
| 45378 | 355.75 | 160.88 | T | 950.1 | A2 | 510.49 | 571 |
| 73721 | 190.75 |  | Q3 | 243.77 | Z2 | 131.48 | 16 |
| 99214 | 129.83 | 83.18 | B |  |  |  | 7544 |

## §8.4 DRG 470 (DOS 2026-10-01)

| ccn | hospital_name | wage_index | relative_weight | operating_base_rate | wage_adjusted_operating | ime_payment | dsh_payment | uncompensated_care | capital_payment | estimated_total_payment |
|---|---|---|---|---|---|---|---|---|---|---|
| 360180 | Cleveland Clinic | 0.8888 | 1.9563 | 6375.87 | 12473.11 | 3772.87 | 303.22 | 1213.76 | 1262.33 | 19102.75 |
| 360051 | Miami Valley Hospital | 0.9182 | 1.9563 | 6500.7 | 12717.32 | 1108.7 | 448.92 | 673.9 | 1156.21 | 16018.31 |
| 360085 | Ohio State University Hospitals | 0.9236 | 1.9563 | 6523.62 | 12762.16 | 2564.94 | 589.48 | 1273.68 | 1074.85 | 18264.86 |

## §8.6 CCN–NPI match, Ohio Type 2 hospital NPIs (NPPES taxonomy 282N*)

| Taxonomy | Subpart | NPIs | No CCN | % |
|---|---|---|---|---|
| 282N00000X | no | 394 | 142 | 36.0% |
| 282N00000X | yes | 48 | 16 | 33.3% |
| 282NC0060X | no | 62 | 15 | 24.2% |
| 282NC0060X | yes | 14 | 2 | 14.3% |
| 282NC2000X | no | 35 | 8 | 22.9% |
| 282NR1301X | no | 15 | 4 | 26.7% |
| 282NR1301X | yes | 1 | 0 | 0.0% |
| 282NW0100X | no | 1 | 0 | 0.0% |

## §8.7 sources (page, file, SHA-256, load date)

| Table | Release | File | SHA-256 | Loaded | CMS page |
|---|---|---|---|---|---|
| ref_ambulance | CY2026 | AMBULANCE/2026 | 41658147eac5a162 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance/ambulance-fee-schedule-public-use-files |
| ref_ambulance | CY2025 | AMBULANCE/2025 | c1dbbdba39fe2eb2 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance/ambulance-fee-schedule-public-use-files |
| ref_ambulance | CY2024 | AMBULANCE/2024 | 41f8221a775cac3d | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance/ambulance-fee-schedule-public-use-files |
| ref_anesthesia_base_units | CY2022 | ANESTHESIA | 9bf71b437a1061b1 | 2026-10-18 | https://www.cms.gov/medicare/payment/fee-schedules/physician/anesthesiologists-center |
| ref_anesthesia_cf | 2024D | MPFS2024D | 2604538d8f6b8265 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24d |
| ref_anesthesia_cf | 2026D | MPFS | 51afbeb853bce73c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26d |
| ref_anesthesia_cf | 2025D | MPFS2025 | 5f5c944453462828 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25d-0 |
| ref_anesthesia_cf | 2024C | MPFS2024 | 6f333a2f554ee30c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24c |
| ref_anesthesia_cf | 2024B | MPFS2024B | b6ba19357dca0565 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24b |
| ref_anesthesia_cf | 2024A | MPFS2024A | 55c3fb57e2377f7b | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24a |
| ref_anesthesia_cf | 2025A | MPFS2025A | 8bc4c67526656b78 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25a |
| ref_anesthesia_cf | 2025B | MPFS2025B | 1fff318c974812d9 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25b |
| ref_anesthesia_cf | 2025C | MPFS2025C | c50de068a8263312 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25c |
| ref_anesthesia_cf | 2026A | MPFS2026A | 6eacf966b1e740d9 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26a |
| ref_anesthesia_cf | 2026B | MPFS2026B | 8aea553288e44804 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26b |
| ref_anesthesia_cf | 2026C | MPFS2026C | c7fe4e5b4bbb9499 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26c |
| ref_asc | 2026Q4 | ASC | af16cc05f7a46296 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2025Q4 | ASC2025 | 265ebba2496d31ca | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2024Q4 | ASC2024 | 33b68627f4886baa | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2024Q1 | ASC2024A | 2608a7ca655217f9 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2024Q2 | ASC2024B | 00b7a5125f6e40ff | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2024Q3 | ASC2024C | 8ac759d830f72cda | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2025Q1 | ASC2025A | 8c57e464f81c2091 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2025Q2 | ASC2025B | 92c35a8b7e6211e8 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2025Q3 | ASC2025C | f83806c69a3a35e1 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2026Q1 | ASC2026A | 51f77275e93877a9 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2026Q2 | ASC2026B | 74ccae7b4005208f | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asc | 2026Q3 | ASC2026C | 833cb837897eb290 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/ambulatory-surgical-center-asc/asc-payment-rates-addenda |
| ref_asp | 2024Q1 | ASP/2024Q1 | 5e9560bc0a375755 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2024Q2 | ASP/2024Q2 | 23480cb404ef36e4 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2024Q3 | ASP/2024Q3 | 147d7640ffdc35e4 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2024Q4 | ASP/2024Q4 | b3b8a01ee581954b | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2025Q1 | ASP/2025Q1 | 8f78af585136166c | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2025Q2 | ASP/2025Q2 | b64130c917a32f4a | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2025Q3 | ASP/2025Q3 | 2731498d1a69d0f5 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2025Q4 | ASP/2025Q4 | 6fd67a403973d969 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2026Q1 | ASP/2026Q1 | ee3a4b9a4a2690d7 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2026Q2 | ASP/2026Q2 | faa5d054d262ddc3 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2026Q3 | ASP/2026Q3 | a345acd5d3750d08 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_asp | 2026Q4 | ASP/2026Q4 | 0d1e10450c178612 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ccn_npi | 2026-07 | ENROLLMENTS | c09f7db4dfbc2e8a | 2026-10-19 | https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/hospital-enrollments |
| ref_chow | 2026-09 | OWNERSHIP/2026-10 | f60a1b48967dc9f4 | 2026-10-21 | https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/hospital-change-of-ownership |
| ref_chow_npi | 2026-09 | OWNERSHIP/2026-10 | f60a1b48967dc9f4 | 2026-10-21 | https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/hospital-change-of-ownership |
| ref_clfs | 2026Q4 | CLFS/2026Q4 | 36e3ee8769971686 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/26clabq4 |
| ref_clfs | 2025Q4 | CLFS/2025Q4 | f133417147f4c942 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/25clabq4 |
| ref_clfs | 2024Q4 | CLFS/2024Q4 | a95268fa972965ef | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/24clabq4 |
| ref_clfs | 2024Q1 | CLFS/2024Q1 | 180b90dff4386b2e | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/24clabq1 |
| ref_clfs | 2024Q2 | CLFS/2024Q2 | d178ce7cd501885b | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/24clabq2 |
| ref_clfs | 2024Q3 | CLFS/2024Q3 | c4d9c87d8edbcd8f | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/24clabq3 |
| ref_clfs | 2025Q1 | CLFS/2025Q1 | 3a6ae381501ee77a | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/25clabq1 |
| ref_clfs | 2025Q2 | CLFS/2025Q2 | 97b70c0d1b46d71c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/25clabq2 |
| ref_clfs | 2025Q3 | CLFS/2025Q3 | 166efc2b2ddddf11 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/25clabq3 |
| ref_clfs | 2026Q1 | CLFS/2026Q1 | 5be760b9fc8660c5 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/26clabq1 |
| ref_clfs | 2026Q2 | CLFS/2026Q2 | 43c81064de5bf84a | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/26clabq2 |
| ref_clfs | 2026Q3 | CLFS/2026Q3 | 179e916d69121b89 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/clinical-laboratory-fee-schedule-clfs/files/26clabq3 |
| ref_code_specialty | CY2024 | UTILIZATION | 0893456869f155e0 | 2026-10-18 | https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service |
| ref_dmepos | 2026D | DMEPOS/2026D | b87e69dda8d536c7 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-d |
| ref_dmepos | 2025D | DMEPOS/2025D | e0fbe6dcdb1c76ac | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-d |
| ref_dmepos | 2024D | DMEPOS/2024D | bab7fd9782ea6604 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-d |
| ref_dmepos | 2024A | DMEPOS/2024A | a8c8018778cebb5e | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-a |
| ref_dmepos | 2024B | DMEPOS/2024B | 52997b1ee2bf8e83 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-b |
| ref_dmepos | 2024C | DMEPOS/2024C | 77ee941845a5a23a | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-c |
| ref_dmepos | 2025A | DMEPOS/2025A | 9c9d9d0584b1ee9c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-a |
| ref_dmepos | 2025B | DMEPOS/2025B | 33454976cd03f9cd | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-b |
| ref_dmepos | 2025C | DMEPOS/2025C | 8005fbc76747ae80 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-c |
| ref_dmepos | 2026A | DMEPOS/2026A | ba175cc113bf2a57 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-a |
| ref_dmepos | 2026B | DMEPOS/2026B | 5b65b9f15a0c6f55 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-b |
| ref_dmepos | 2026C | DMEPOS/2026C | d367d30b6d036dfe | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-c |
| ref_dmepos_rural_zip | 2026D | DMEPOS/2026D | b87e69dda8d536c7 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-d |
| ref_dmepos_rural_zip | 2025D | DMEPOS/2025D | e0fbe6dcdb1c76ac | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-d |
| ref_dmepos_rural_zip | 2024D | DMEPOS/2024D | bab7fd9782ea6604 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-d |
| ref_dmepos_rural_zip | 2024A | DMEPOS/2024A | a8c8018778cebb5e | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-a |
| ref_dmepos_rural_zip | 2024B | DMEPOS/2024B | 52997b1ee2bf8e83 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-b |
| ref_dmepos_rural_zip | 2024C | DMEPOS/2024C | 77ee941845a5a23a | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme24-c |
| ref_dmepos_rural_zip | 2025A | DMEPOS/2025A | 9c9d9d0584b1ee9c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-a |
| ref_dmepos_rural_zip | 2025B | DMEPOS/2025B | 33454976cd03f9cd | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-b |
| ref_dmepos_rural_zip | 2025C | DMEPOS/2025C | 8005fbc76747ae80 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme25-c |
| ref_dmepos_rural_zip | 2026A | DMEPOS/2026A | ba175cc113bf2a57 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-a |
| ref_dmepos_rural_zip | 2026B | DMEPOS/2026B | 5b65b9f15a0c6f55 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-b |
| ref_dmepos_rural_zip | 2026C | DMEPOS/2026C | d367d30b6d036dfe | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/dmepos/dmepos-fee-schedule/dme26-c |
| ref_geo | 2024Q1 | HUD/2024Q1 | 608fbacc8bf83098 | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2024Q2 | HUD/2024Q2 | 38a7348936adfd2a | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2024Q3 | HUD/2024Q3 | d14e1d3267175dec | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2024Q4 | HUD/2024Q4 | 7dc6254b77ed582f | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2025Q1 | HUD/2025Q1 | bf49ecf00d902cdc | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2025Q2 | HUD/2025Q2 | badf8809ada85670 | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2025Q3 | HUD/2025Q3 | 578c2c160fd8da3c | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2025Q4 | HUD/2025Q4 | add03ab8c2767ecc | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2026Q1 | HUD/2026Q1 | 95f54243886cc5ba | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo | 2026Q2 | HUD/2026Q2 | 8554296b3a708d29 | 2026-10-21 | https://www.huduser.gov/portal/datasets/usps_crosswalk.html |
| ref_geo_zcta_county | 2020 | CENSUS/ZCTA2020 | 62d92d379a4c3349 | 2026-10-21 | https://www.census.gov/geographies/reference-files/time-series/geo/relationship-files.html |
| ref_hcpcs_code | 2024Q1 | HCPCS/2024Q1 | a038387f62f59851 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2024Q2 | HCPCS/2024Q2 | 109489d49a2408d3 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2024Q3 | HCPCS/2024Q3 | fc150c855ea16359 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2024Q4 | HCPCS/2024Q4 | 2ffbc24cd15395dc | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2025Q1 | HCPCS/2025Q1 | e934df67bb951772 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2025Q2 | HCPCS/2025Q2 | bdd84807958b35f6 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2025Q3 | HCPCS/2025Q3 | 90d5ea712e11cba3 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2025Q4 | HCPCS/2025Q4 | 8f80b5b076ea09c2 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2026Q1 | HCPCS/2026Q1 | d7e3a387555f5c05 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2026Q2 | HCPCS/2026Q2 | d8f2b2dd1295a10b | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2026Q3 | HCPCS/2026Q3 | 0a7a74609cb9970a | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcpcs_code | 2026Q4 | HCPCS/2026Q4 | e526da8e8616ecc0 | 2026-10-22 | https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update |
| ref_hcris | FY2023 | HCRIS/HOSP10FY2023 | c66a0f1683596338 | 2026-10-17 | https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year |
| ref_hcris | FY2024 | HCRIS/HOSP10FY2024 | f288f704f227c0b2 | 2026-10-17 | https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year |
| ref_hcris | FY2025 | HCRIS/HOSP10FY2025 | 5aca20a2c5d3f540 | 2026-10-17 | https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year |
| ref_hcris | FY2026 | HCRIS/HOSP10FY2026 | de7fbd886285fe67 | 2026-10-17 | https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year |
| ref_ipps_drg | FY2027 | IPPS/FY2027/cms-1849-fr-and-cn-table-5.zip | 3b43654767907b1c | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2027-ipps-final-rule-home-page |
| ref_ipps_drg | FY2026 | IPPS/FY2026/cms-1833-f-table-5.zip | 14dba6b8f06ab819 | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2026-ipps-final-rule-home-page |
| ref_ipps_drg | FY2025 | IPPS/FY2025/fy2025-ipps-final-rule-and-correction-notice-table-5.zip | d5e0a0bd231412e1 | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2025-ipps-final-rule-home-page |
| ref_ipps_hospital | FY2027 | IPPS/FY2027/fy-2027-ipps-fr-cn-impact-file.zip | 6e51b1015b6c5c93 | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2027-ipps-final-rule-home-page |
| ref_ipps_hospital | FY2026 | IPPS/FY2026/fy_2026_ipps_final_rule_impact_file.zip | c19ae04778a7018f | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2026-ipps-final-rule-home-page |
| ref_ipps_hospital | FY2025 | IPPS/FY2025/fy_2025_ipps_impact_file-fr-cn-ifc.zip | 1b650a7f96eef459 | 2026-10-18 | https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2025-ipps-final-rule-home-page |
| ref_mpfs | 2024D | MPFS2024D | 2604538d8f6b8265 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24d |
| ref_mpfs | 2026D | MPFS | 51afbeb853bce73c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26d |
| ref_mpfs | 2024B | MPFS2024B | b6ba19357dca0565 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24b |
| ref_mpfs | 2024C | MPFS2024 | 6f333a2f554ee30c | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24c |
| ref_mpfs | 2025D | MPFS2025 | 5f5c944453462828 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25d-0 |
| ref_mpfs | 2024A | MPFS2024A | 55c3fb57e2377f7b | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu24a |
| ref_mpfs | 2025A | MPFS2025A | 8bc4c67526656b78 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25a |
| ref_mpfs | 2025B | MPFS2025B | 1fff318c974812d9 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25b |
| ref_mpfs | 2025C | MPFS2025C | c50de068a8263312 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu25c |
| ref_mpfs | 2026A | MPFS2026A | 6eacf966b1e740d9 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26a |
| ref_mpfs | 2026B | MPFS2026B | 8aea553288e44804 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26b |
| ref_mpfs | 2026C | MPFS2026C | c7fe4e5b4bbb9499 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26c |
| ref_mpfs_locality | 2026D | MPFS | 51afbeb853bce73c | 2026-10-17 | https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26d |
| ref_mue | 2026Q4/hospital | NCCI/facilityoutpatienthospitalservicesmuetable-effective-10-01-2026 | f174b39ddcaf08fe | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edits |
| ref_mue | 2026Q4/practitioner | NCCI/practitionerservicesmuetable-effective-10-01-2026 | e165bcd1e39ee0db | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edits |
| ref_mue | 2025Q4/hospital | MUE2025/hospital | 5a6593e69c8fba7b | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q4/practitioner | MUE2025/practitioner | 90acec749e1f03f5 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q4/hospital | MUE2024/hospital | 58da99490a301a85 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q4/practitioner | MUE2024/practitioner | 4205f956af329093 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q1/hospital | MUE2024A/hospital | 76d6075fc988e138 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q1/practitioner | MUE2024A/practitioner | 2d670114795fa732 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q2/hospital | MUE2024B/hospital | 19b60926d0e1d6ec | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q2/practitioner | MUE2024B/practitioner | 4478e01e6208ca8b | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q3/hospital | MUE2024C/hospital | 65098cb1292d498f | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2024Q3/practitioner | MUE2024C/practitioner | 06b9378e968b349c | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q1/hospital | MUE2025A/hospital | aafdacf073fd63e9 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q1/practitioner | MUE2025A/practitioner | 86ce15fce2cd42ec | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q2/hospital | MUE2025B/hospital | 3097c3df389807f3 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q2/practitioner | MUE2025B/practitioner | fb97746498c8166c | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q3/hospital | MUE2025C/hospital | 35ae92a8e89f9ad0 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2025Q3/practitioner | MUE2025C/practitioner | 1679c026f8a8cbec | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q1/hospital | MUE2026A/hospital | 0ffee7f6d05a694c | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q1/practitioner | MUE2026A/practitioner | 96543e747e763d72 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q2/hospital | MUE2026B/hospital | 79a93446622b2582 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q2/practitioner | MUE2026B/practitioner | 2e504c35d76c301c | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q3/hospital | MUE2026C/hospital | 49a57f35234feeea | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_mue | 2026Q3/practitioner | MUE2026C/practitioner | c3ae164122f0f901 | 2026-10-19 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edit-mue-archive |
| ref_nadac | NADAC2024 | NADAC/2024 | 272d312694c015c6 | 2026-10-21 | https://data.medicaid.gov/dataset/99315a95-37ac-4eee-946a-3c523b4c481e |
| ref_nadac | NADAC2025 | NADAC/2025 | 8c5b1ca7ccf0118c | 2026-10-21 | https://data.medicaid.gov/datasets?keyword=nadac%202025 |
| ref_nadac | NADAC2026 | NADAC/2026 | 0845572e512132ee | 2026-10-21 | https://data.medicaid.gov/dataset/fbb83258-11c7-47f5-8b18-5f8e79f7e704 |
| ref_ncci_ptp | 2026Q4/hospital | NCCI/PTP/ccioph-v323r0-f1.zip | fdf7651190e17f60 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/hospital | NCCI/PTP/ccioph-v323r0-f2.zip | 5f39fb6295824ad7 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/hospital | NCCI/PTP/ccioph-v323r0-f3.zip | e323c7c723c9a8ba | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/hospital | NCCI/PTP/ccioph-v323r0-f4.zip | 0e731c4c0f5a2150 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/practitioner | NCCI/PTP/ccipra-v323r0-f1.zip | 40adc15de0b5cf94 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/practitioner | NCCI/PTP/ccipra-v323r0-f2.zip | e0c916cc5b0bf1b7 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/practitioner | NCCI/PTP/ccipra-v323r0-f3.zip | 79024324e5f2ac96 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ncci_ptp | 2026Q4/practitioner | NCCI/PTP/ccipra-v323r0-f4.zip | 028a6d91e27ab177 | 2026-10-17 | https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits |
| ref_ndc_hcpcs | 2024Q1 | ASP/2024Q1 | 5e9560bc0a375755 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2024Q2 | ASP/2024Q2 | 23480cb404ef36e4 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2024Q3 | ASP/2024Q3 | 147d7640ffdc35e4 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2024Q4 | ASP/2024Q4 | b3b8a01ee581954b | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2025Q1 | ASP/2025Q1 | 8f78af585136166c | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2025Q2 | ASP/2025Q2 | b64130c917a32f4a | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2025Q3 | ASP/2025Q3 | 2731498d1a69d0f5 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2025Q4 | ASP/2025Q4 | 6fd67a403973d969 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2026Q1 | ASP/2026Q1 | ee3a4b9a4a2690d7 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2026Q2 | ASP/2026Q2 | faa5d054d262ddc3 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2026Q3 | ASP/2026Q3 | a345acd5d3750d08 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_hcpcs | 2026Q4 | ASP/2026Q4 | 0d1e10450c178612 | 2026-10-22 | https://www.cms.gov/medicare/payment/part-b-drugs/asp-pricing-files |
| ref_ndc_package | 2026-10 | FDA_NDC/2026-10 | 0bbf87f08dcc2b15 | 2026-10-21 | https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory |
| ref_ndc_product | 2026-10 | FDA_NDC/2026-10 | 0bbf87f08dcc2b15 | 2026-10-21 | https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory |
| ref_opps | 2026Q4 | OPPS | 0b2483f46bd2fe93 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates/october-2026-addendum-b |
| ref_opps | 2025Q4 | OPPS2025 | c044636bbb871017 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates/october-2025-addendum-b |
| ref_opps | 2024Q4 | OPPS2024 | a5500da0c2ce1066 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient/addendum-a-b-updates/october-2024-updated-10/02/2024-0 |
| ref_opps | 2024Q1 | OPPS2024A | cd0094a6114f2d05 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2024Q2 | OPPS2024B | 4175fce3d363bd24 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2024Q3 | OPPS2024C | 0f51593ebf1f2f07 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2025Q1 | OPPS2025A | 5f7ed650a467ce9e | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2025Q2 | OPPS2025B | 033b02a032543976 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2025Q3 | OPPS2025C | 296e0e00061a0379 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2026Q1 | OPPS2026A | 7a15f0ecd0280cd3 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2026Q2 | OPPS2026B | 25b666a7023c190b | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_opps | 2026Q3 | OPPS2026C | 8dc631d3dce30ee3 | 2026-10-19 | https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates |
| ref_ownership | 2026-09 | OWNERSHIP/2026-10 | f60a1b48967dc9f4 | 2026-10-21 | https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/hospital-all-owners |
| ref_provider | 2026-10 | NPES | b22e2fac1cef4575 | 2026-10-17 | https://download.cms.gov/nppes/NPI_Files.html |
| ref_provider | 2026-10 | NPES/NPPES Deactivated NPI Report 20261012.xlsx | 0552b3192932726c | 2026-10-17 | https://download.cms.gov/nppes/NPI_Files.html |
| ref_quality_asc | 2026-09 | CARECOMPARE/2026-10 | 2aac9fdd370d8166 | 2026-10-21 | https://data.cms.gov/provider-data/topics/hospitals |
| ref_quality_hospital | 2026-09 | CARECOMPARE/2026-10 | 2aac9fdd370d8166 | 2026-10-21 | https://data.cms.gov/provider-data/topics/hospitals |
| ref_quality_measure | 2026-09 | CARECOMPARE/2026-10 | 2aac9fdd370d8166 | 2026-10-21 | https://data.cms.gov/provider-data/topics/hospitals |
| ref_zip_locality | 2026-08 | ZIPLOC/2026 | a2060fccf48a1bed | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules |
| ref_zip_locality | 2026Q4 | AMBULANCE/2026 | 41658147eac5a162 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance |
| ref_zip_locality | 2025EOY | AMBULANCE/2025 | c1dbbdba39fe2eb2 | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance |
| ref_zip_locality | 2024EOY | AMBULANCE/2024 | 41f8221a775cac3d | 2026-10-19 | https://www.cms.gov/medicare/payment/fee-schedules/ambulance |

## §8.6 Ohio acute-care NPIs (282N00000X, not subparts) by category

| Category | NPIs | No CCN |
|---|---|---|
| closed | 6 | 6 |
| federal | 20 | 20 |
| hospital | 174 | 1 |
| not_acute | 6 | 6 |
| not_hospital | 42 | 28 |
| stale | 146 | 81 |

## §8.2 providers in the first market (Ohio + border zip3)

| Part | Metro | Entity type | NPIs |
|---|---|---|---|
| border | Cincinnati / Northern Kentucky | 1 | 6,887 |
| border | Cincinnati / Northern Kentucky | 2 | 1,873 |
| border | Cincinnati / SE Indiana | 1 | 1,000 |
| border | Cincinnati / SE Indiana | 2 | 372 |
| border | Huntington / Ironton / Portsmouth | 1 | 20,435 |
| border | Huntington / Ironton / Portsmouth | 2 | 2,681 |
| border | Parkersburg / Marietta | 1 | 5,239 |
| border | Parkersburg / Marietta | 2 | 715 |
| border | Toledo / Monroe | 1 | 75,277 |
| border | Toledo / Monroe | 2 | 18,366 |
| border | Wheeling / Steubenville | 1 | 3,819 |
| border | Wheeling / Steubenville | 2 | 740 |
| border | Youngstown / Sharon | 1 | 5,536 |
| border | Youngstown / Sharon | 2 | 2,102 |
| ohio | Ohio | 1 | 343,394 |
| ohio | Ohio | 2 | 66,569 |

## §8.2 providers by practice state and entity type

| State | Entity type | NPIs |
|---|---|---|
| (blank) | 1 | 2 |
| (blank) | None | 357,925 |
| (other text) | 1 | 3,053 |
| (other text) | 2 | 1,278 |
| AA | 1 | 428 |
| AA | 2 | 10 |
| AB | 1 | 24 |
| AB | 2 | 1 |
| AE | 1 | 3,295 |
| AE | 2 | 150 |
| AF | 1 | 1 |
| AK | 1 | 29,551 |
| AK | 2 | 6,646 |
| AL | 1 | 69,753 |
| AL | 2 | 25,730 |
| AP | 1 | 2,434 |
| AP | 2 | 130 |
| AR | 1 | 69,303 |
| AR | 2 | 17,743 |
| AS | 1 | 197 |
| AS | 2 | 37 |
| AU | 1 | 1 |
| AZ | 1 | 130,543 |
| AZ | 2 | 47,165 |
| BC | 1 | 74 |
| BC | 2 | 137 |
| BE | 1 | 1 |
| BO | 1 | 1 |
| BW | 1 | 2 |
| CA | 1 | 997,505 |
| CA | 2 | 198,647 |
| CE | 1 | 64 |
| CN | 1 | 1 |
| CO | 1 | 153,023 |
| CO | 2 | 45,982 |
| CT | 1 | 85,708 |
| CT | 2 | 20,466 |
| DC | 1 | 47,655 |
| DC | 2 | 5,454 |
| DE | 1 | 21,717 |
| DE | 2 | 6,382 |
| EO | 1 | 1 |
| ES | 1 | 2 |
| EU | 1 | 2 |
| FI | 2 | 1 |
| FL | 1 | 482,622 |
| FL | 2 | 174,998 |
| FM | 1 | 10 |
| FM | 2 | 3 |
| FP | 1 | 1 |
| GA | 1 | 172,427 |
| GA | 2 | 59,902 |
| GB | 1 | 4 |
| GE | 1 | 4 |
| GE | 2 | 1 |
| GU | 1 | 901 |
| GU | 2 | 286 |
| HI | 1 | 32,958 |
| HI | 2 | 8,261 |
| IA | 1 | 49,815 |
| IA | 2 | 16,596 |
| ID | 1 | 34,407 |
| ID | 2 | 12,178 |
| IL | 1 | 246,684 |
| IL | 2 | 74,618 |
| IN | 1 | 123,447 |
| IN | 2 | 33,429 |
| JA | 1 | 1 |
| JA | 2 | 1 |
| JJ | 1 | 1 |
| JP | 1 | 2 |
| KL | 1 | 1 |
| KR | 1 | 1 |
| KS | 1 | 56,549 |
| KS | 2 | 16,692 |
| KY | 1 | 89,196 |
| KY | 2 | 24,777 |
| LA | 1 | 93,819 |
| LA | 2 | 32,596 |
| LB | 1 | 1 |
| MA | 1 | 223,359 |
| MA | 2 | 36,666 |
| MB | 1 | 5 |
| MD | 1 | 163,625 |
| MD | 2 | 54,238 |
| ME | 1 | 34,403 |
| ME | 2 | 9,101 |
| MH | 1 | 1 |
| MH | 2 | 2 |
| MI | 1 | 294,428 |
| MI | 2 | 66,203 |
| MN | 1 | 137,213 |
| MN | 2 | 32,560 |
| MO | 1 | 114,995 |
| MO | 2 | 34,475 |
| MP | 1 | 209 |
| MP | 2 | 114 |
| MS | 1 | 41,560 |
| MS | 2 | 16,754 |
| MT | 1 | 22,513 |
| MT | 2 | 7,652 |
| MX | 1 | 6 |
| MX | 2 | 2 |
| NA | 1 | 7 |
| NA | 2 | 1 |
| NB | 1 | 2 |
| NC | 1 | 205,340 |
| NC | 2 | 73,793 |
| ND | 1 | 23,040 |
| ND | 2 | 4,842 |
| NE | 1 | 81,775 |
| NE | 2 | 12,088 |
| NF | 1 | 1 |
| NH | 1 | 33,681 |
| NH | 2 | 7,274 |
| NJ | 1 | 168,855 |
| NJ | 2 | 66,779 |
| NL | 1 | 4 |
| NL | 2 | 1 |
| NM | 1 | 57,799 |
| NM | 2 | 12,378 |
| NO | 1 | 1 |
| NP | 1 | 1 |
| NS | 1 | 8 |
| NT | 1 | 1 |
| NV | 1 | 102,999 |
| NV | 2 | 21,302 |
| NY | 1 | 555,800 |
| NY | 2 | 105,258 |
| OH | 1 | 343,452 |
| OH | 2 | 66,578 |
| OK | 1 | 94,319 |
| OK | 2 | 23,660 |
| ON | 1 | 102 |
| ON | 2 | 4 |
| OR | 1 | 128,301 |
| OR | 2 | 22,911 |
| PA | 1 | 266,652 |
| PA | 2 | 71,043 |
| PE | 1 | 1 |
| PH | 1 | 1 |
| PI | 1 | 2 |
| PN | 1 | 6 |
| PR | 1 | 41,448 |
| PR | 2 | 16,910 |
| QC | 1 | 23 |
| QC | 2 | 2 |
| QR | 2 | 1 |
| RI | 1 | 26,235 |
| RI | 2 | 6,167 |
| RJ | 1 | 2 |
| RM | 1 | 5 |
| RN | 1 | 1 |
| RP | 1 | 4 |
| RS | 1 | 1 |
| SA | 1 | 5 |
| SC | 1 | 88,717 |
| SC | 2 | 28,652 |
| SD | 1 | 17,738 |
| SD | 2 | 5,593 |
| SE | 1 | 1 |
| SG | 1 | 1 |
| SK | 1 | 9 |
| SK | 2 | 2 |
| SN | 2 | 5 |
| TE | 1 | 1 |
| TH | 1 | 1 |
| TI | 1 | 1 |
| TN | 1 | 128,647 |
| TN | 2 | 32,838 |
| TO | 2 | 1 |
| TX | 1 | 444,288 |
| TX | 2 | 167,889 |
| UK | 1 | 4 |
| UK | 2 | 2 |
| UP | 1 | 1 |
| US | 1 | 6 |
| UT | 1 | 80,049 |
| UT | 2 | 16,451 |
| VA | 1 | 153,071 |
| VA | 2 | 49,398 |
| VI | 1 | 745 |
| VI | 2 | 511 |
| VT | 1 | 15,650 |
| VT | 2 | 3,647 |
| WA | 1 | 208,018 |
| WA | 2 | 36,950 |
| WC | 1 | 1 |
| WI | 1 | 119,315 |
| WI | 2 | 26,468 |
| WV | 1 | 82,375 |
| WV | 2 | 10,084 |
| WY | 1 | 14,069 |
| WY | 2 | 4,614 |
| XX | 1 | 1 |
| ZA | 1 | 1 |
| ZH | 1 | 1 |
