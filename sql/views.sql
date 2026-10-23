-- Views and macros over the ref_* tables. Run by `build_duckdb` after the
-- tables are copied in. Each statement is separated by a line "-- @stmt".
-- A statement whose tables are not loaded yet is skipped and reported.

-- @stmt mpfs_rate: physician fee schedule rate on a date of service
CREATE OR REPLACE MACRO mpfs_rate(p_code, p_dos, p_carrier := '15202', p_locality := '00', p_modifier := '') AS TABLE
SELECT hcpcs, modifier, carrier, locality, status_code,
       rate_nonfacility, rate_facility, opps_cap_applied,
       effective_start, effective_end, period, source_file, source_sha256
FROM ref_mpfs
WHERE hcpcs = p_code AND modifier = p_modifier
  AND carrier = p_carrier AND locality = p_locality
  AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt ncci_pairs_on_date: PTP edits in effect on a date of service
CREATE OR REPLACE MACRO ncci_pairs_on_date(p_code, p_dos, p_setting := 'practitioner') AS TABLE
SELECT setting, column_1, column_2, modifier_indicator, rationale,
       effective_start, deletion_date
FROM ref_ncci_ptp
WHERE (column_1 = p_code OR column_2 = p_code) AND setting = p_setting
  AND is_applicable
  AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt code_profile: Spec Â§8.3 â€” one row per code with every Step 1 rate
CREATE OR REPLACE MACRO code_profile(p_dos, p_carrier := '15202', p_locality := '00') AS TABLE
WITH codes AS (
    SELECT DISTINCT hcpcs FROM ref_mpfs WHERE CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end
    UNION SELECT DISTINCT hcpcs FROM ref_opps WHERE CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end
    UNION SELECT DISTINCT hcpcs FROM ref_asc  WHERE CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end
)
SELECT c.hcpcs,
       m.rate_nonfacility AS mpfs_nonfacility,
       m.rate_facility    AS mpfs_facility,
       o.status_indicator AS opps_si,
       o.payment_rate_national AS opps_national,
       a.payment_indicator AS asc_pi,
       a.payment_rate     AS asc_rate,
       (SELECT count(*) FROM ref_ncci_ptp n
         WHERE (n.column_1 = c.hcpcs OR n.column_2 = c.hcpcs) AND n.is_applicable
           AND CAST(p_dos AS DATE) BETWEEN n.effective_start AND n.effective_end) AS ncci_pairs
FROM codes c
LEFT JOIN ref_mpfs m ON m.hcpcs = c.hcpcs AND m.modifier = '' AND m.carrier = p_carrier
      AND m.locality = p_locality AND CAST(p_dos AS DATE) BETWEEN m.effective_start AND m.effective_end
LEFT JOIN ref_opps o ON o.hcpcs = c.hcpcs AND CAST(p_dos AS DATE) BETWEEN o.effective_start AND o.effective_end
LEFT JOIN ref_asc  a ON a.hcpcs = c.hcpcs AND CAST(p_dos AS DATE) BETWEEN a.effective_start AND a.effective_end;

-- @stmt v_provider_first_market: Spec Â§4 query-time filter (Ohio + border zip3)
CREATE OR REPLACE VIEW v_provider_first_market AS
SELECT p.*, g.market_part, g.metro
FROM ref_provider p
JOIN cfg_first_market_zip3 g ON g.zip3 = p.zip3
WHERE (g.market_part = 'ohio' AND p.practice_state = 'OH')
   OR (g.market_part = 'border' AND p.practice_state = g.state);

-- @stmt v_hcris_latest: newest primary cost report per hospital
CREATE OR REPLACE VIEW v_hcris_latest AS
SELECT * FROM ref_hcris WHERE is_primary
QUALIFY row_number() OVER (PARTITION BY ccn ORDER BY fy_end DESC) = 1;

-- @stmt opps_wage_adjusted: Spec Â§6 table 3 â€” hospital-specific OPPS rate
-- (needs ref_ipps_hospital, table 4; skipped until it is loaded)
CREATE OR REPLACE MACRO opps_wage_adjusted(p_code, p_dos, p_ccn) AS TABLE
SELECT o.hcpcs, h.ccn, o.payment_rate_national,
       h.wage_index,
       round(o.payment_rate_national * (0.60 * h.wage_index + 0.40), 2) AS payment_rate_adjusted
FROM ref_opps o
JOIN ref_ipps_hospital h ON h.ccn = p_ccn
     AND CAST(p_dos AS DATE) BETWEEN h.effective_start AND h.effective_end
WHERE o.hcpcs = p_code AND CAST(p_dos AS DATE) BETWEEN o.effective_start AND o.effective_end;

-- @stmt ipps_payment: Spec Â§8.4 â€” IPPS payment for one MS-DRG at one hospital
-- wage_adjusted_operating = (labor x wage index + nonlabor x COLA) x DRG weight.
-- The estimate adds the per-hospital factors from the impact file: VBP and
-- readmission proxies on the base DRG amount, IME, DSH, uncompensated-care
-- per claim, low-volume factor, and capital (federal rate x GAF x weight x
-- (1 + capital IME + capital DSH)). Outliers, transfers, new-technology add-on
-- payments, and hospital-specific rates (SCH/MDH) are not included.
CREATE OR REPLACE MACRO ipps_payment(p_drg, p_dos, p_ccn) AS TABLE
WITH x AS (
  SELECT d.ms_drg, d.ms_drg_title, d.relative_weight, h.ccn, h.hospital_name, h.state,
         h.wage_index, h.operating_base_rate, h.capital_base_rate, h.ime_operating, h.dsh_operating,
         h.ucp_per_claim, h.vbp_factor, h.hrrp_factor, h.low_volume_factor, h.ime_capital,
         h.dsh_capital, h.provider_type, d.fiscal_year,
         h.operating_base_rate * d.relative_weight AS op_drg
  FROM ref_ipps_drg d
  JOIN ref_ipps_hospital h
    ON CAST(p_dos AS DATE) BETWEEN h.effective_start AND h.effective_end
   AND h.ccn = p_ccn
  WHERE d.ms_drg = lpad(CAST(p_drg AS VARCHAR), 3, '0')
    AND CAST(p_dos AS DATE) BETWEEN d.effective_start AND d.effective_end
)
SELECT ms_drg, ms_drg_title, fiscal_year, ccn, hospital_name, state, wage_index, relative_weight,
       operating_base_rate,
       round(op_drg, 2)                                              AS wage_adjusted_operating,
       round(op_drg * (vbp_factor + hrrp_factor - 1), 2)             AS operating_after_vbp_hrrp,
       round(op_drg * ime_operating, 2)                              AS ime_payment,
       round(op_drg * dsh_operating, 2)                              AS dsh_payment,
       round(ucp_per_claim, 2)                                       AS uncompensated_care,
       round(capital_base_rate * relative_weight * (1 + ime_capital + dsh_capital), 2) AS capital_payment,
       round((op_drg * (vbp_factor + hrrp_factor - 1) + op_drg * ime_operating + op_drg * dsh_operating)
             * low_volume_factor + ucp_per_claim
             + capital_base_rate * relative_weight * (1 + ime_capital + dsh_capital), 2) AS estimated_total_payment,
       provider_type
FROM x;

-- @stmt hospital_npis: Table 8 â€” every NPI for a hospital CCN (and the reverse)
CREATE OR REPLACE MACRO hospital_npis(p_ccn) AS TABLE
SELECT ccn, npi, match_source, organization_name, dba_name, state, enrollment_id, provider_type_text
FROM ref_ccn_npi WHERE ccn = p_ccn ORDER BY match_source, npi;

-- @stmt v_ccn_npi_ohio_report: Spec Â§6 â€” Ohio Type 2 hospital NPIs (NPPES 282N*) and their CCN match.
-- npi_category says why an NPI can or cannot have a CCN:
--   federal       VA / military hospitals: not enrolled in Medicare, so no CCN exists
--   not_hospital  a person, physician group, pharmacy, staffing firm... filed with a hospital taxonomy,
--                 or a home address (APT)
--   stale         NPPES record not updated since 2019 (often a closed or renamed hospital)
--   hospital      everything else: should have a CCN
--   closed / not_acute / not_hospital (reviewed): set by hand in config/ccn_npi_reclass.csv
--                 with a reason and a source; it overrides the rules above
CREATE OR REPLACE VIEW v_ccn_npi_ohio_report AS
WITH p AS (
  SELECT p.*, upper(coalesce(p.provider_name, '')) AS nm, upper(coalesce(p.practice_address_1, '')) AS ad
  FROM ref_provider p
  WHERE p.entity_type = 2 AND p.practice_state = 'OH' AND NOT p.is_deactivated
    AND p.primary_taxonomy LIKE '282N%'
)
SELECT p.npi, p.provider_name, p.primary_taxonomy, coalesce(p.is_subpart, '') AS is_subpart, p.practice_address_1,
       p.practice_city, p.zip5, p.last_update_date,
       coalesce(r.category, CASE
         WHEN regexp_matches(nm, '\b(VA|VAMC|LVA|VETERAN|VETERANS|AIR FORCE|ARMY|NAVY|AFB)\b')
           OR upper(coalesce(p.practice_city, '')) LIKE '%AFB%' THEN 'federal'
         WHEN regexp_matches(ad, '\bAPT\b')
           OR regexp_matches(nm, '\b(M\.?D\.?|D\.?O\.?|PHARMACY|PHARMASOURCE|RPH|CHILDCARE|SPORTS|ANESTHESIA|RADIOLOGY|PHYSICIANS?|HOSPITALISTS|MINUTE CLINIC|SUPPLEMENTAL|STAFFING|BIRTH|COUNSELING|INTERNAL MEDICINE|OBSERVATION MEDICINE|MEDICAL ASSOCIATES|PROFESSIONAL|UCPHA|HOME CARE|DRUG TREATMENT|DEPARTMENT OF RADIOLOGY|PREXUS|EVERWELL|COORDINATED CARE)\b')
           OR NOT regexp_matches(nm, '(HOSPITAL|MEDICAL|HEALTH|CENTER|CENTRE|CLINIC|UNIVERSITY|UNIVERISTY|UNVERSITY|SYSTEM|CARE|FOUNDATION|FOUNDATON|INSTITUTE|LLC|L\.L\.C|INC|CORP|COMPANY|\bCO\b|ASSOCIATION|PARTNERS|HEALLTH|PREMIERHEALTH|TRIHEALTH|OHIOHEALTH|DHSC|VAMC)')
           THEN 'not_hospital'
         WHEN p.last_update_date < DATE '2020-01-01' THEN 'stale'
         ELSE 'hospital'
       END) AS npi_category,
       r.reason AS reclass_reason,
       (SELECT string_agg(DISTINCT c.ccn, ';') FROM ref_ccn_npi c WHERE c.npi = p.npi) AS ccns,
       (SELECT string_agg(DISTINCT c.match_source, ';') FROM ref_ccn_npi c WHERE c.npi = p.npi) AS match_sources
FROM p LEFT JOIN cfg_ccn_npi_reclass r ON r.npi = p.npi;

-- @stmt specialty_plausible: Table 9 â€” can this specialty / taxonomy plausibly bill this code?
-- Returns one row per Medicare specialty; filter on p_taxonomy to test an NPPES taxonomy.
CREATE OR REPLACE MACRO specialty_plausible(p_code) AS TABLE
SELECT hcpcs, medicare_specialty, specialty_rank, specialty_share, specialty_services, plausible,
       list(DISTINCT taxonomy ORDER BY taxonomy) FILTER (WHERE taxonomy IS NOT NULL) AS taxonomies
FROM ref_code_specialty WHERE hcpcs = p_code
GROUP BY ALL ORDER BY specialty_rank;

-- @stmt clfs_rate: Table 11 â€” lab fee schedule national limit on a date of service
CREATE OR REPLACE MACRO clfs_rate(p_code, p_dos, p_modifier := '') AS TABLE
SELECT hcpcs, modifier, rate, indicator, period, effective_start, effective_end, source_file
FROM ref_clfs
WHERE hcpcs = p_code AND modifier = p_modifier
  AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt dmepos_fee: Table 12 â€” DMEPOS fee for a state; uses the rural fee when the zip is a DMEPOS rural zip
CREATE OR REPLACE MACRO dmepos_fee(p_code, p_dos, p_state, p_zip := NULL, p_modifier := '', p_modifier2 := '') AS TABLE
SELECT d.hcpcs, d.modifier, d.modifier2, d.state, d.category, d.fee_nonrural, d.fee_rural,
       (r.zip5 IS NOT NULL) AS zip_is_rural,
       CASE WHEN r.zip5 IS NOT NULL AND d.fee_rural IS NOT NULL THEN d.fee_rural ELSE d.fee_nonrural END AS fee,
       d.period, d.source_file
FROM ref_dmepos d
LEFT JOIN ref_dmepos_rural_zip r
  ON r.zip5 = p_zip AND CAST(p_dos AS DATE) BETWEEN r.effective_start AND r.effective_end
WHERE d.hcpcs = p_code AND d.modifier = p_modifier AND d.modifier2 = p_modifier2 AND d.state = p_state
  AND CAST(p_dos AS DATE) BETWEEN d.effective_start AND d.effective_end;

-- @stmt ambulance_rate: Table 13 â€” ambulance amount for the pickup zip (urban / rural / super rural)
CREATE OR REPLACE MACRO ambulance_rate(p_code, p_dos, p_zip) AS TABLE
SELECT a.hcpcs, z.zip5, z.state, a.carrier, a.locality, z.rural_indicator, a.is_mileage,
       a.rate_urban, a.rate_rural, a.rate_super_rural, a.rate_rural_miles_1_17,
       CASE z.rural_indicator
         WHEN 'B' THEN coalesce(a.rate_super_rural, a.rate_rural)
         WHEN 'R' THEN a.rate_rural
         ELSE a.rate_urban END AS rate,
       a.period, a.source_file
FROM ref_zip_locality z
JOIN ref_ambulance a
  ON a.carrier = z.carrier AND a.locality = z.locality AND a.hcpcs = p_code
 AND CAST(p_dos AS DATE) BETWEEN a.effective_start AND a.effective_end
WHERE z.zip5 = p_zip
  AND CAST(p_dos AS DATE) BETWEEN z.effective_start AND z.effective_end;

-- @stmt anesthesia_payment: Table 14 â€” (base units + minutes / 15) x anesthesia CF for a locality
CREATE OR REPLACE MACRO anesthesia_payment(p_code, p_minutes, p_dos, p_carrier := '15202', p_locality := '00') AS TABLE
SELECT b.hcpcs, b.base_units, round(p_minutes / 15.0, 2) AS time_units, c.anesthesia_cf,
       round((b.base_units + p_minutes / 15.0) * c.anesthesia_cf, 2) AS payment,
       c.carrier, c.locality, c.period AS cf_period
FROM ref_anesthesia_base_units b
JOIN ref_anesthesia_cf c
  ON c.carrier = p_carrier AND c.locality = p_locality
 AND CAST(p_dos AS DATE) BETWEEN c.effective_start AND c.effective_end
WHERE b.hcpcs = p_code
  AND CAST(p_dos AS DATE) BETWEEN b.effective_start AND b.effective_end;

-- ===================================================================== Spec Â§11

-- @stmt v_hospital_owners: owners of each hospital CCN (ownership x CCNâ€“NPI enrollments)
CREATE OR REPLACE VIEW v_hospital_owners AS
SELECT DISTINCT c.ccn, c.npi, o.enrollment_id, o.organization_name, o.owner_name, o.owner_type,
       o.role_code, o.role_text, o.percentage_ownership, o.association_date, o.dataset
FROM ref_ownership o
JOIN ref_ccn_npi c ON c.enrollment_id = o.enrollment_id;

-- @stmt zip_geo: county and CBSA of a zip on a date (largest residential share first)
CREATE OR REPLACE MACRO zip_geo(p_zip, p_dos) AS TABLE
SELECT zip5, geo_type, geoid, city, state, res_ratio, tot_ratio, period
FROM ref_geo
WHERE zip5 = p_zip AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end
ORDER BY geo_type, res_ratio DESC;

-- @stmt drug_price: NADAC price of a package NDC on a date, with the FDA names
CREATE OR REPLACE MACRO drug_price(p_ndc11, p_dos) AS TABLE
SELECT n.ndc, n.ndc_description, n.nadac_per_unit, n.pricing_unit, n.classification,
       n.effective_start, n.effective_end, p.proprietary_name, p.nonproprietary_name,
       p.labeler_name, k.package_description
FROM ref_nadac n
LEFT JOIN ref_ndc_package k ON k.ndc11 = n.ndc
LEFT JOIN ref_ndc_product p ON p.product_id = k.product_id
WHERE n.ndc = p_ndc11 AND CAST(p_dos AS DATE) BETWEEN n.effective_start AND n.effective_end;

-- @stmt asp_price: Medicare Part B payment limit (ASP + 6 %) of a HCPCS code on a date
CREATE OR REPLACE MACRO asp_price(p_hcpcs, p_dos) AS TABLE
SELECT hcpcs, description, dosage, payment_limit, coinsurance_pct, notes, period,
       effective_start, effective_end, source_file, source_sha256
FROM ref_asp
WHERE hcpcs = upper(p_hcpcs) AND price_type = 'ASP'
  AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt ndc_asp: HCPCS code, billable units and Medicare payment for one NDC package on a date
CREATE OR REPLACE MACRO ndc_asp(p_ndc11, p_dos) AS TABLE
SELECT x.ndc, x.ndc11, x.hcpcs, x.drug_name, x.labeler, x.dosage, x.bill_units_pkg,
       a.payment_limit, a.payment_limit * x.bill_units_pkg AS payment_per_package,
       x.crosswalk_type, x.period
FROM ref_ndc_hcpcs x
LEFT JOIN ref_asp a ON a.hcpcs = x.hcpcs AND a.price_type = 'ASP' AND a.period = x.period
WHERE x.ndc11 = p_ndc11 AND x.crosswalk_type IN ('ASP', 'OPPS', 'AWP', 'PREP')
  AND CAST(p_dos AS DATE) BETWEEN x.effective_start AND x.effective_end;

-- @stmt hcpcs_info: HCPCS Level II code on a date: names, status, dose unit in the descriptor
CREATE OR REPLACE MACRO hcpcs_info(p_hcpcs, p_dos) AS TABLE
SELECT hcpcs, long_description, short_description, dose_from_description, pricing_indicator,
       coverage_code, betos, added_date, termination_date, action_code, period
FROM ref_hcpcs_code
WHERE hcpcs = upper(p_hcpcs) AND record_type = 'code'
  AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;


-- ===== Step 2 and later (added 2026-10-22) =====

-- views_mrf.sql: hospital price files (Step 2) in DuckDB.
-- Run after load_mrf.py:   python peek.py  or  duckdb data\meshkor.duckdb < views_mrf.sql
-- Or paste the CREATE statements into sql\views.sql so build_duckdb makes them every time.

-- One view over every loaded hospital / period (Hive folders ccn=â€¦ / period=â€¦).
-- @stmt ref_hospital_mrf: added from the Step 2 view files
CREATE OR REPLACE VIEW ref_hospital_mrf AS
SELECT * FROM read_parquet('data/ref/ref_hospital_mrf/*/*/*.parquet', hive_partitioning = true, hive_types = {'ccn': VARCHAR, 'period': VARCHAR}, union_by_name = true);

-- Negotiated rate for a HCPCS code at a hospital on a date of service, one row per payer/plan.
-- @stmt mrf_rate: added from the Step 2 view files
CREATE OR REPLACE MACRO mrf_rate(p_ccn, p_code, dos) AS TABLE
SELECT ccn, hospital_name, period, hcpcs, rc, setting, payer_name, plan_name,
       gross_charge, discounted_cash, negotiated_dollar, negotiated_percentage, negotiated_algorithm,
       estimated_amount, median_amount, pct_10, pct_90, methodology, charge_min, charge_max,
       source_file, source_sha256
FROM ref_hospital_mrf
WHERE ccn = p_ccn AND hcpcs = p_code AND dos BETWEEN effective_start AND effective_end;

-- Inpatient stay by MS-DRG at a hospital on a date of service.
-- @stmt mrf_drg: added from the Step 2 view files
CREATE OR REPLACE MACRO mrf_drg(p_ccn, p_drg, dos) AS TABLE
SELECT ccn, hospital_name, period, ms_drg, description, payer_name, plan_name,
       gross_charge, discounted_cash, negotiated_dollar, negotiated_percentage, negotiated_algorithm,
       estimated_amount, methodology, charge_min, charge_max, source_file, source_sha256
FROM ref_hospital_mrf
WHERE ccn = p_ccn AND ms_drg = p_drg AND dos BETWEEN effective_start AND effective_end;

-- Drug rows (J-codes and NDC) for the drug markup audit.
-- @stmt v_mrf_drugs: added from the Step 2 view files
CREATE OR REPLACE VIEW v_mrf_drugs AS
SELECT ccn, hospital_name, period, hcpcs, ndc, description, drug_unit, drug_type, setting,
       payer_name, plan_name, gross_charge, discounted_cash, negotiated_dollar, negotiated_percentage,
       negotiated_algorithm, estimated_amount, median_amount, pct_10, pct_90, methodology,
       effective_start, effective_end, source_file, source_sha256
FROM ref_hospital_mrf
WHERE ndc IS NOT NULL OR hcpcs LIKE 'J%' OR hcpcs LIKE 'Q%';

-- Example queries
-- SELECT * FROM mrf_rate('360085', '27447', DATE '2026-09-01') ORDER BY negotiated_dollar;
-- SELECT * FROM mrf_drg('360085', '470', DATE '2026-09-01');
-- SELECT hcpcs, payer_name, negotiated_dollar FROM v_mrf_drugs WHERE ccn='360085' AND hcpcs='J9299' ORDER BY 3;
-- SELECT ccn, period, count(*) FROM ref_hospital_mrf GROUP BY ALL;
-- views_340b.sql: HRSA 340B covered entities in DuckDB. Paste into sql\views.sql, or run once by hand.

-- @stmt ref_340b_entity: added from the Step 2 view files
CREATE OR REPLACE VIEW ref_340b_entity AS
SELECT * FROM read_parquet('data/ref/ref_340b_entity/*/*.parquet', hive_partitioning = true, hive_types = {'period': VARCHAR}, union_by_name = true);

-- @stmt ref_340b_shipping: added from the Step 2 view files
CREATE OR REPLACE VIEW ref_340b_shipping AS
SELECT * FROM read_parquet('data/ref/ref_340b_shipping/*/*.parquet', hive_partitioning = true, hive_types = {'period': VARCHAR}, union_by_name = true);

-- @stmt ref_340b_contract_pharmacy: added from the Step 2 view files
CREATE OR REPLACE VIEW ref_340b_contract_pharmacy AS
SELECT * FROM read_parquet('data/ref/ref_340b_contract_pharmacy/*/*.parquet', hive_partitioning = true, hive_types = {'period': VARCHAR}, union_by_name = true);

-- Is this hospital (CCN) a 340B covered entity on a date? One row per 340B registration.
-- @stmt hospital_340b: added from the Step 2 view files
CREATE OR REPLACE MACRO hospital_340b(p_ccn, dos) AS TABLE
SELECT id_340b, entity_type, entity_name, entity_sub_division_name, participating,
       participating_start_date, termination_date, street_city, street_state, period
FROM ref_340b_entity
WHERE ccn = p_ccn
  AND participating_start_date <= dos
  AND (termination_date IS NULL OR termination_date > dos);

-- Ohio hospitals in 340B (parent registrations only: TYPE+CCN, or TYPE+CCN-00; child sites have letter or -NN suffixes)
-- @stmt v_340b_ohio_hospitals: added from the Step 2 view files
CREATE OR REPLACE VIEW v_340b_ohio_hospitals AS
SELECT ccn, entity_type, entity_name, street_city, participating, participating_start_date, termination_date, period
FROM ref_340b_entity
WHERE street_state = 'OH' AND ccn IS NOT NULL AND regexp_matches(id_340b, '^[A-Z]{2,5}[0-9]{6}(-00)?$')
  AND entity_type IN ('DSH','CAN','CAH','RRC','SCH','PED','CH');

-- Examples
-- SELECT * FROM hospital_340b('360242', DATE '2026-09-01');
-- SELECT entity_type, count(*) FROM v_340b_ohio_hospitals WHERE participating GROUP BY 1;
-- views_msdrg.sql: MS-DRG definitions in DuckDB. Paste into sql\views.sql, or run once by hand.

-- @stmt ref_msdrg: added from the Step 2 view files
CREATE OR REPLACE VIEW ref_msdrg AS
SELECT * FROM read_parquet('data/ref/ref_msdrg/*/*.parquet', hive_partitioning = true, hive_types = {'period': VARCHAR}, union_by_name = true);
-- @stmt ref_msdrg_dx: added from the Step 2 view files
CREATE OR REPLACE VIEW ref_msdrg_dx AS
SELECT * FROM read_parquet('data/ref/ref_msdrg_dx/*/*.parquet', hive_partitioning = true, hive_types = {'period': VARCHAR}, union_by_name = true);
-- @stmt ref_msdrg_cc: added from the Step 2 view files
CREATE OR REPLACE VIEW ref_msdrg_cc AS
SELECT * FROM read_parquet('data/ref/ref_msdrg_cc/*/*.parquet', hive_partitioning = true, hive_types = {'period': VARCHAR}, union_by_name = true);
-- @stmt ref_msdrg_cc_excl: added from the Step 2 view files
CREATE OR REPLACE VIEW ref_msdrg_cc_excl AS
SELECT * FROM read_parquet('data/ref/ref_msdrg_cc_excl/*/*.parquet', hive_partitioning = true, hive_types = {'period': VARCHAR}, union_by_name = true);

-- Title, MDC and type of a DRG on a date of service (the grouper version in force that day).
-- @stmt msdrg_title: added from the Step 2 view files
CREATE OR REPLACE MACRO msdrg_title(p_drg, dos) AS TABLE
SELECT ms_drg, mdc, drg_type, title, period AS grouper_version, fiscal_year
FROM ref_msdrg WHERE ms_drg = p_drg AND dos BETWEEN effective_start AND effective_end;

-- Which DRGs a principal diagnosis can lead to on a date of service (from the appendix B index).
-- @stmt msdrg_for_dx: added from the Step 2 view files
CREATE OR REPLACE MACRO msdrg_for_dx(p_icd10, dos) AS TABLE
SELECT d.icd10, d.mdc, d.drg_from, d.drg_to, r.ms_drg, r.title, d.period AS grouper_version
FROM ref_msdrg_dx d
JOIN ref_msdrg r ON r.period = d.period AND r.ms_drg BETWEEN d.drg_from AND d.drg_to
WHERE d.icd10 = p_icd10 AND dos BETWEEN d.effective_start AND d.effective_end
ORDER BY r.ms_drg;

-- Is a secondary diagnosis a CC or MCC on a date of service?
-- @stmt msdrg_cc_level: added from the Step 2 view files
CREATE OR REPLACE MACRO msdrg_cc_level(p_icd10, dos) AS TABLE
SELECT icd10, cc_level, cc_only_if_alive, hac, pdx_exclusion_group, description, period AS grouper_version
FROM ref_msdrg_cc WHERE icd10 = p_icd10 AND dos BETWEEN effective_start AND effective_end;

-- Examples
-- SELECT * FROM msdrg_title('470', DATE '2026-05-01');
-- SELECT * FROM msdrg_for_dx('S72001A', DATE '2026-05-01');   -- hip fracture -> DRGs
-- SELECT * FROM msdrg_cc_level('I5023', DATE '2026-05-01');
