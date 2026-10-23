# verify ref_msdrg

Run: 2026-10-22T23:16:32  Result: **157 pass, 0 fail**

| Check | Result | Detail |
|---|---|---|
| V41.1: raw unchanged appendix_A.txt | PASS |  |
| V41.1: raw unchanged appendix_B.txt | PASS |  |
| V41.1: raw unchanged appendix_C.txt | PASS |  |
| V41.1: raw unchanged icd-10-ms-drg-definitions-manual-files-v411.zip | PASS |  |
| V41.1: raw unchanged medicare-severity-diagnosis-related-group-ms-drg-and-medicare-code-editor-mce-version-v411-java.zip | PASS |  |
| V41.1: ref_msdrg parquet exists | PASS |  |
| V41.1: ref_msdrg_dx parquet exists | PASS |  |
| V41.1: ref_msdrg_cc parquet exists | PASS |  |
| V41.1: ref_msdrg_cc_excl parquet exists | PASS |  |
| V41.1: ref_msdrg rows = DRG lines in appendix A | PASS | 766 = 766 |
| V41.1: ref_msdrg_dx distinct codes = code lines in appendix B | PASS | 65,269 = 65,269 |
| V41.1: ref_msdrg_cc rows = CC/MCC lines in appendix C part 1 | PASS | 18,215 = 18,215 |
| V41.1: ref_msdrg has no duplicate DRG | PASS | 0 |
| V41.1: every DRG is 3 digits with a title | PASS | 0 |
| V41.1: every DRG in appendix B exists in appendix A | PASS | 0 unknown DRGs |
| V41.1: cc_level is CC or MCC | PASS | 0 |
| V41.1: CC descriptions hold no exclusion-group fragments | PASS | 0 |
| V41.1: cc exclusions (part 3) loaded or absent in this version (info) | PASS | 0 rows |
| V41.1: DRG 470 title | PASS | MAJOR HIP AND KNEE JOINT REPLACEMENT OR REATTACHMENT OF LOWE |
| V41.1: DRG 291 title | PASS | HEART FAILURE AND SHOCK WITH MCC |
| V41.1: DRG 871 title | PASS | SEPTICEMIA OR SEVERE SEPSIS WITHOUT MV >96 HOURS WITH MCC |
| V41.1: lineage filled | PASS |  |
| V41: raw unchanged appendix_A.txt | PASS |  |
| V41: raw unchanged appendix_B.txt | PASS |  |
| V41: raw unchanged appendix_C.txt | PASS |  |
| V41: raw unchanged icd-10-ms-drg-definitions-manual-files-v41.zip | PASS |  |
| V41: raw unchanged ms-drg-mce-v41-javasourcecode-binaries.zip | PASS |  |
| V41: ref_msdrg parquet exists | PASS |  |
| V41: ref_msdrg_dx parquet exists | PASS |  |
| V41: ref_msdrg_cc parquet exists | PASS |  |
| V41: ref_msdrg_cc_excl parquet exists | PASS |  |
| V41: ref_msdrg rows = DRG lines in appendix A | PASS | 766 = 766 |
| V41: ref_msdrg_dx distinct codes = code lines in appendix B | PASS | 65,269 = 65,269 |
| V41: ref_msdrg_cc rows = CC/MCC lines in appendix C part 1 | PASS | 18,215 = 18,215 |
| V41: ref_msdrg has no duplicate DRG | PASS | 0 |
| V41: every DRG is 3 digits with a title | PASS | 0 |
| V41: every DRG in appendix B exists in appendix A | PASS | 0 unknown DRGs |
| V41: cc_level is CC or MCC | PASS | 0 |
| V41: CC descriptions hold no exclusion-group fragments | PASS | 0 |
| V41: cc exclusions (part 3) loaded or absent in this version (info) | PASS | 0 rows |
| V41: DRG 470 title | PASS | MAJOR HIP AND KNEE JOINT REPLACEMENT OR REATTACHMENT OF LOWE |
| V41: DRG 291 title | PASS | HEART FAILURE AND SHOCK WITH MCC |
| V41: DRG 871 title | PASS | SEPTICEMIA OR SEVERE SEPSIS WITHOUT MV >96 HOURS WITH MCC |
| V41: lineage filled | PASS |  |
| V42.1: raw unchanged appendix_A.txt | PASS |  |
| V42.1: raw unchanged appendix_B.txt | PASS |  |
| V42.1: raw unchanged appendix_C.txt | PASS |  |
| V42.1: raw unchanged icd-10-ms-drg-definitions-manual-files-v42.1.zip | PASS |  |
| V42.1: raw unchanged medicare-severity-diagnosis-related-group-ms-drg-and-medicare-code-editor-mce-version-42-java-source.zip | PASS |  |
| V42.1: ref_msdrg parquet exists | PASS |  |
| V42.1: ref_msdrg_dx parquet exists | PASS |  |
| V42.1: ref_msdrg_cc parquet exists | PASS |  |
| V42.1: ref_msdrg_cc_excl parquet exists | PASS |  |
| V42.1: ref_msdrg rows = DRG lines in appendix A | PASS | 773 = 773 |
| V42.1: ref_msdrg_dx distinct codes = code lines in appendix B | PASS | 65,481 = 65,481 |
| V42.1: ref_msdrg_cc rows = CC/MCC lines in appendix C part 1 | PASS | 18,305 = 18,305 |
| V42.1: ref_msdrg has no duplicate DRG | PASS | 0 |
| V42.1: every DRG is 3 digits with a title | PASS | 0 |
| V42.1: every DRG in appendix B exists in appendix A | PASS | 0 unknown DRGs |
| V42.1: cc_level is CC or MCC | PASS | 0 |
| V42.1: CC descriptions hold no exclusion-group fragments | PASS | 0 |
| V42.1: cc exclusions (part 3) loaded or absent in this version (info) | PASS | 6,152 rows |
| V42.1: DRG 470 title | PASS | Major Hip and Knee Joint Replacement or Reattachment of Lowe |
| V42.1: DRG 291 title | PASS | Heart Failure and Shock with MCC |
| V42.1: DRG 871 title | PASS | Septicemia or Severe Sepsis without MV >96 Hours with MCC |
| V42.1: lineage filled | PASS |  |
| V42: raw unchanged appendix_A.txt | PASS |  |
| V42: raw unchanged appendix_B.txt | PASS |  |
| V42: raw unchanged appendix_C.txt | PASS |  |
| V42: raw unchanged msdrgv420icd10r0definitionsmanualtext.zip | PASS |  |
| V42: raw unchanged standalone-jars.zip | PASS |  |
| V42: ref_msdrg parquet exists | PASS |  |
| V42: ref_msdrg_dx parquet exists | PASS |  |
| V42: ref_msdrg_cc parquet exists | PASS |  |
| V42: ref_msdrg_cc_excl parquet exists | PASS |  |
| V42: ref_msdrg rows = DRG lines in appendix A | PASS | 773 = 773 |
| V42: ref_msdrg_dx distinct codes = code lines in appendix B | PASS | 65,481 = 65,481 |
| V42: ref_msdrg_cc rows = CC/MCC lines in appendix C part 1 | PASS | 18,305 = 18,305 |
| V42: ref_msdrg has no duplicate DRG | PASS | 0 |
| V42: every DRG is 3 digits with a title | PASS | 0 |
| V42: every DRG in appendix B exists in appendix A | PASS | 0 unknown DRGs |
| V42: cc_level is CC or MCC | PASS | 0 |
| V42: CC descriptions hold no exclusion-group fragments | PASS | 0 |
| V42: cc exclusions (part 3) loaded or absent in this version (info) | PASS | 6,152 rows |
| V42: DRG 470 title | PASS | Major Hip and Knee Joint Replacement or Reattachment of Lowe |
| V42: DRG 291 title | PASS | Heart Failure and Shock with MCC |
| V42: DRG 871 title | PASS | Septicemia or Severe Sepsis without MV >96 Hours with MCC |
| V42: lineage filled | PASS |  |
| V42: DRG count = ref_ipps_drg FY2025 (Table 5) | PASS | 773 = 773 |
| V43.1: raw unchanged appendix_A.txt | PASS |  |
| V43.1: raw unchanged appendix_B.txt | PASS |  |
| V43.1: raw unchanged appendix_C.txt | PASS |  |
| V43.1: raw unchanged icd10-ms-drg-definitions-manual-files-v43-1.zip | PASS |  |
| V43.1: raw unchanged ms-drg-mce-v43-1-standalone-jars.zip | PASS |  |
| V43.1: ref_msdrg parquet exists | PASS |  |
| V43.1: ref_msdrg_dx parquet exists | PASS |  |
| V43.1: ref_msdrg_cc parquet exists | PASS |  |
| V43.1: ref_msdrg_cc_excl parquet exists | PASS |  |
| V43.1: ref_msdrg rows = DRG lines in appendix A | PASS | 772 = 772 |
| V43.1: ref_msdrg_dx distinct codes = code lines in appendix B | PASS | 65,925 = 65,925 |
| V43.1: ref_msdrg_cc rows = CC/MCC lines in appendix C part 1 | PASS | 18,432 = 18,432 |
| V43.1: ref_msdrg has no duplicate DRG | PASS | 0 |
| V43.1: every DRG is 3 digits with a title | PASS | 0 |
| V43.1: every DRG in appendix B exists in appendix A | PASS | 0 unknown DRGs |
| V43.1: cc_level is CC or MCC | PASS | 0 |
| V43.1: CC descriptions hold no exclusion-group fragments | PASS | 0 |
| V43.1: cc exclusions (part 3) loaded or absent in this version (info) | PASS | 6,188 rows |
| V43.1: DRG 470 title | PASS | Major Hip and Knee Joint Replacement or Reattachment of Lowe |
| V43.1: DRG 291 title | PASS | Heart Failure and Shock with MCC |
| V43.1: DRG 871 title | PASS | Septicemia or Severe Sepsis without MV >96 Hours with MCC |
| V43.1: lineage filled | PASS |  |
| V43: raw unchanged appendix_A.txt | PASS |  |
| V43: raw unchanged appendix_B.txt | PASS |  |
| V43: raw unchanged appendix_C.txt | PASS |  |
| V43: raw unchanged icd10-ms-drg-definitions-manual-files-v43.zip | PASS |  |
| V43: raw unchanged ms-drg-mce-v43-standalone-jars.zip | PASS |  |
| V43: ref_msdrg parquet exists | PASS |  |
| V43: ref_msdrg_dx parquet exists | PASS |  |
| V43: ref_msdrg_cc parquet exists | PASS |  |
| V43: ref_msdrg_cc_excl parquet exists | PASS |  |
| V43: ref_msdrg rows = DRG lines in appendix A | PASS | 772 = 772 |
| V43: ref_msdrg_dx distinct codes = code lines in appendix B | PASS | 65,925 = 65,925 |
| V43: ref_msdrg_cc rows = CC/MCC lines in appendix C part 1 | PASS | 18,432 = 18,432 |
| V43: ref_msdrg has no duplicate DRG | PASS | 0 |
| V43: every DRG is 3 digits with a title | PASS | 0 |
| V43: every DRG in appendix B exists in appendix A | PASS | 0 unknown DRGs |
| V43: cc_level is CC or MCC | PASS | 0 |
| V43: CC descriptions hold no exclusion-group fragments | PASS | 0 |
| V43: cc exclusions (part 3) loaded or absent in this version (info) | PASS | 6,188 rows |
| V43: DRG 470 title | PASS | Major Hip and Knee Joint Replacement or Reattachment of Lowe |
| V43: DRG 291 title | PASS | Heart Failure and Shock with MCC |
| V43: DRG 871 title | PASS | Septicemia or Severe Sepsis without MV >96 Hours with MCC |
| V43: lineage filled | PASS |  |
| V43: DRG count = ref_ipps_drg FY2026 (Table 5) | PASS | 772 = 772 |
| V44: raw unchanged appendix_A.txt | PASS |  |
| V44: raw unchanged appendix_B.txt | PASS |  |
| V44: raw unchanged appendix_C.txt | PASS |  |
| V44: raw unchanged fy2027-fr-icd10-ms-drg-definitions-manual-files-v44.zip | PASS |  |
| V44: raw unchanged ms-drg-mce-v44-java-jars.zip | PASS |  |
| V44: ref_msdrg parquet exists | PASS |  |
| V44: ref_msdrg_dx parquet exists | PASS |  |
| V44: ref_msdrg_cc parquet exists | PASS |  |
| V44: ref_msdrg_cc_excl parquet exists | PASS |  |
| V44: ref_msdrg rows = DRG lines in appendix A | PASS | 768 = 768 |
| V44: ref_msdrg_dx distinct codes = code lines in appendix B | PASS | 66,085 = 66,085 |
| V44: ref_msdrg_cc rows = CC/MCC lines in appendix C part 1 | PASS | 18,470 = 18,470 |
| V44: ref_msdrg has no duplicate DRG | PASS | 0 |
| V44: every DRG is 3 digits with a title | PASS | 0 |
| V44: every DRG in appendix B exists in appendix A | PASS | 0 unknown DRGs |
| V44: cc_level is CC or MCC | PASS | 0 |
| V44: CC descriptions hold no exclusion-group fragments | PASS | 0 |
| V44: cc exclusions (part 3) loaded or absent in this version (info) | PASS | 6,189 rows |
| V44: DRG 470 title | PASS | Major Hip and Knee Joint Replacement or Reattachment of Lowe |
| V44: DRG 291 title | PASS | Heart Failure and Shock with MCC |
| V44: DRG 871 title | PASS | Septicemia or Severe Sepsis without MV >96 Hours with MCC |
| V44: lineage filled | PASS |  |
| V44: DRG count = ref_ipps_drg FY2027 (Table 5) | PASS | 768 = 768 |