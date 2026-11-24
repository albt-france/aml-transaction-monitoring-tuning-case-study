-- Assertions. Each named query returns one boolean in its first column; src/run_sql.py fails if any is false.

-- name: test_parquet_rows_equal_csv_rows
SELECT (SELECT count(*) FROM tx_raw) = (SELECT rows_in_csv FROM read_json_auto('{PARQ}/meta.json')) AS ok;

-- name: test_bank_feed_rows
SELECT (SELECT count(*) FROM tx) = (SELECT sum(n_rows) FROM daily_volume WHERE day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period))
                                 + (SELECT count(*) FROM read_parquet('{SIM}/payroll_batch.parquet')) AS ok;

-- name: test_no_raw_account_number_in_outputs
SELECT count(*) = 0 AS ok FROM read_text('{OUT}/*.csv') WHERE regexp_matches(content, '(^|[^.0-9A-Za-z])[0-9A-F]{9}($|[^0-9A-Za-z])');

-- name: test_no_raw_account_number_in_sim_tables
SELECT count(*) = 0 AS ok FROM (
    SELECT account_ref AS v FROM read_parquet('{SIM}/alerts.parquet')
    UNION ALL SELECT account_ref FROM read_parquet('{SIM}/payroll_batch.parquet')
    UNION ALL SELECT entity_ref FROM read_parquet('{SIM}/customers.parquet'))
WHERE NOT regexp_matches(v, '^(ACC|ENT)_[0-9]{6}$');

-- name: test_no_entity_name_column
SELECT count(*) = 0 AS ok FROM (DESCRIBE SELECT * FROM read_parquet('{PARQ}/accounts.parquet')) WHERE column_name ILIKE '%name%';

-- name: test_published_groups_at_least_5
SELECT (SELECT min(visible_attempts) FROM read_csv_auto('{OUT}/typology_coverage.csv')) >= 5
   AND (SELECT min(customers) FROM read_csv_auto('{OUT}/kyc_by_segment.csv')) >= 5
   AND (SELECT min(customers) FROM read_csv_auto('{OUT}/bm_bank_n_book.csv')) >= 5 AS ok;

-- name: test_every_alert_has_one_decision
SELECT (SELECT count(*) FROM alerts) = (SELECT count(*) FROM dispositions)
   AND (SELECT count(*) FROM alerts a LEFT JOIN dispositions d USING (alert_id) WHERE d.alert_id IS NULL) = 0 AS ok;

-- name: test_alert_ids_unique
SELECT count(*) = count(DISTINCT alert_id) AS ok FROM alerts;

-- name: test_documented_and_implemented_differ_only_where_declared
SELECT count(*) = 3 AS ok FROM read_csv_auto('{OUT}/doc_vs_code.csv') WHERE gap;

-- name: test_precision_between_0_and_1
SELECT bool_and(precision IS NULL OR precision BETWEEN 0 AND 1) AS ok FROM read_csv_auto('{OUT}/rule_performance.csv');

-- name: test_payroll_spike_not_escalated
SELECT escalated = 0 AND laundering_hits = 0 AS ok FROM read_csv_auto('{OUT}/payroll_verdict.csv');
