-- ===== Step 2: hospital price files, MS-DRG definitions, 340B (added 2026-10-23) =====
-- build_duckdb makes the tables ref_hospital_mrf, ref_msdrg*, ref_340b_* from their Parquet
-- folders. Only macros and views here, one per "-- @stmt" block, like the Step 1 ones above.

-- @stmt mrf_rate: a hospital's posted rates for a HCPCS/CPT code on a date of service, one row per payer/plan
CREATE OR REPLACE MACRO mrf_rate(p_ccn, p_code, p_dos) AS TABLE
SELECT ccn, hospital_name, period, hcpcs, rc, setting, payer_group, payer_name, plan_name,
       gross_charge, discounted_cash, negotiated_dollar, negotiated_percentage, negotiated_algorithm,
       estimated_amount, median_amount, pct_10, pct_90, rate_count, methodology, charge_min, charge_max,
       last_updated_on, source_file, source_sha256
FROM ref_hospital_mrf
WHERE ccn = p_ccn AND hcpcs = p_code AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt mrf_rc_rate: the same for a revenue-code-only bill line (no HCPCS on the line)
CREATE OR REPLACE MACRO mrf_rc_rate(p_ccn, p_rc, p_dos) AS TABLE
SELECT ccn, hospital_name, period, rc, cdm, description, setting, payer_group, payer_name, plan_name,
       gross_charge, discounted_cash, negotiated_dollar, negotiated_percentage, negotiated_algorithm,
       estimated_amount, methodology, charge_min, charge_max, source_file, source_sha256
FROM ref_hospital_mrf
WHERE ccn = p_ccn AND rc = p_rc AND hcpcs IS NULL AND ms_drg IS NULL
  AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt mrf_drg: a hospital's posted rates for an inpatient MS-DRG on a date of service
CREATE OR REPLACE MACRO mrf_drg(p_ccn, p_drg, p_dos) AS TABLE
SELECT ccn, hospital_name, period, ms_drg, description, payer_group, payer_name, plan_name,
       gross_charge, discounted_cash, negotiated_dollar, negotiated_percentage, negotiated_algorithm,
       estimated_amount, methodology, charge_min, charge_max, source_file, source_sha256
FROM ref_hospital_mrf
WHERE ccn = p_ccn AND ms_drg = p_drg AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt mrf_rate_summary: one row per payer group for a code: min, median, max of the dollar rates, plus cash and gross
CREATE OR REPLACE MACRO mrf_rate_summary(p_ccn, p_code, p_dos) AS TABLE
SELECT ccn, hcpcs, payer_group, count(*) AS plans,
       min(negotiated_dollar) AS min_rate, median(negotiated_dollar) AS median_rate, max(negotiated_dollar) AS max_rate,
       sum(CASE WHEN negotiated_dollar IS NULL AND negotiated_percentage IS NOT NULL THEN 1 ELSE 0 END) AS pct_only_plans,
       max(discounted_cash) AS discounted_cash, max(gross_charge) AS gross_charge,
       any_value(source_file) AS source_file, any_value(source_sha256) AS source_sha256
FROM ref_hospital_mrf
WHERE ccn = p_ccn AND hcpcs = p_code AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end
GROUP BY ccn, hcpcs, payer_group ORDER BY median_rate NULLS LAST;

-- @stmt v_mrf_drugs: drug rows (J/Q codes or an NDC) for the drug markup audit
CREATE OR REPLACE VIEW v_mrf_drugs AS
SELECT ccn, hospital_name, period, hcpcs, ndc, description, drug_unit, drug_type, setting,
       payer_group, payer_name, plan_name, gross_charge, discounted_cash, negotiated_dollar,
       negotiated_percentage, negotiated_algorithm, estimated_amount, median_amount, pct_10, pct_90,
       methodology, effective_start, effective_end, source_file, source_sha256
FROM ref_hospital_mrf
WHERE ndc IS NOT NULL OR hcpcs LIKE 'J%' OR hcpcs LIKE 'Q%';

-- @stmt v_mrf_coverage: which hospitals and periods are loaded, with row counts and file dates
CREATE OR REPLACE VIEW v_mrf_coverage AS
SELECT ccn, any_value(hospital_name) AS hospital_name, period, any_value(last_updated_on) AS file_dated,
       min(effective_start) AS effective_start, max(effective_end) AS effective_end,
       count(*) AS rows_, count(DISTINCT payer_name) AS payers, any_value(source_layout) AS layout,
       any_value(source_sha256) AS source_sha256
FROM ref_hospital_mrf GROUP BY ccn, period ORDER BY ccn, period;

-- @stmt msdrg_title: title, MDC and type of a DRG on a date of service (grouper version in force that day)
CREATE OR REPLACE MACRO msdrg_title(p_drg, p_dos) AS TABLE
SELECT ms_drg, mdc, drg_type, title, period AS grouper_version, fiscal_year
FROM ref_msdrg WHERE ms_drg = p_drg AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt msdrg_for_dx: DRGs a principal diagnosis can lead to on a date of service (appendix B index)
CREATE OR REPLACE MACRO msdrg_for_dx(p_icd10, p_dos) AS TABLE
SELECT d.icd10, d.mdc, d.drg_from, d.drg_to, r.ms_drg, r.title, d.period AS grouper_version
FROM ref_msdrg_dx d
JOIN ref_msdrg r ON r.period = d.period AND r.ms_drg BETWEEN d.drg_from AND d.drg_to
WHERE d.icd10 = p_icd10 AND CAST(p_dos AS DATE) BETWEEN d.effective_start AND d.effective_end
ORDER BY r.ms_drg;

-- @stmt msdrg_cc_level: is a secondary diagnosis a CC or MCC on a date of service
CREATE OR REPLACE MACRO msdrg_cc_level(p_icd10, p_dos) AS TABLE
SELECT icd10, cc_level, cc_only_if_alive, hac, pdx_exclusion_group, description, period AS grouper_version
FROM ref_msdrg_cc WHERE icd10 = p_icd10 AND CAST(p_dos AS DATE) BETWEEN effective_start AND effective_end;

-- @stmt hospital_340b: 340B registrations of a hospital (CCN) active on a date
CREATE OR REPLACE MACRO hospital_340b(p_ccn, p_dos) AS TABLE
SELECT id_340b, entity_type, entity_name, entity_sub_division_name, participating,
       participating_start_date, termination_date, street_city, street_state, period
FROM ref_340b_entity
WHERE ccn = p_ccn AND participating_start_date <= CAST(p_dos AS DATE)
  AND (termination_date IS NULL OR termination_date > CAST(p_dos AS DATE));

-- @stmt v_340b_ohio_hospitals: Ohio hospitals in 340B (parent registrations only)
CREATE OR REPLACE VIEW v_340b_ohio_hospitals AS
SELECT ccn, entity_type, entity_name, street_city, participating, participating_start_date, termination_date, period
FROM ref_340b_entity
WHERE street_state = 'OH' AND ccn IS NOT NULL AND regexp_matches(id_340b, '^[A-Z]{2,5}[0-9]{6}(-00)?$')
  AND entity_type IN ('DSH','CAN','CAH','RRC','SCH','PED','CH');
