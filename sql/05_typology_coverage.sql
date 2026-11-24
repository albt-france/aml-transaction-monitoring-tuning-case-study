-- Typology coverage: which IBM laundering typologies (Patterns file, PUBLIC DATA synthetic) the rules see.
-- An attempt is "visible" to Bank N when at least one of its accounts is in the book and it starts in the window.
-- A rule "detects" an attempt when it raises a true-positive alert on one of the attempt's book accounts
-- between the attempt's first day and its last day + 2 days.

CREATE OR REPLACE TABLE attempts AS
WITH m AS (
    SELECT attempt_id, typology, CAST(ts AS DATE) AS d, from_key AS acct_key FROM patterns
    UNION ALL SELECT attempt_id, typology, CAST(ts AS DATE), to_key FROM patterns
)
SELECT attempt_id, any_value(typology) AS typology, min(d) AS d_start, max(d) AS d_end,
       count(DISTINCT acct_key) AS n_accounts,
       count(DISTINCT acct_key) FILTER (WHERE acct_key IN (SELECT acct_key FROM book)) AS n_book_accounts
FROM m GROUP BY attempt_id;

CREATE OR REPLACE TABLE attempt_book_accounts AS
SELECT DISTINCT p.attempt_id, k.acct_key
FROM patterns p, LATERAL (SELECT p.from_key AS acct_key UNION ALL SELECT p.to_key) k
WHERE k.acct_key IN (SELECT acct_key FROM book);

CREATE OR REPLACE TABLE visible_attempts AS
SELECT * FROM attempts WHERE n_book_accounts > 0 AND d_start <= (SELECT d1 FROM period);

CREATE OR REPLACE MACRO detected_by(alert_table) AS TABLE
SELECT DISTINCT v.attempt_id, a.rule_id
FROM visible_attempts v
JOIN attempt_book_accounts ab USING (attempt_id)
JOIN query_table(alert_table) a ON a.acct_key = ab.acct_key AND a.is_tp = 1
     AND a.day BETWEEN v.d_start AND v.d_end + 2;

CREATE OR REPLACE TABLE detections AS
SELECT 'implemented' AS ruleset, * FROM detected_by('alerts_implemented')
UNION ALL SELECT 'documented', * FROM detected_by('alerts_documented');

-- name: typology_coverage_matrix
SELECT v.typology, r.rule_id,
       count(DISTINCT d.attempt_id) / count(DISTINCT v.attempt_id) AS share_detected,
       count(DISTINCT v.attempt_id) AS visible_attempts,
       list_contains(string_split(replace(any_value(r.typology), ' ', ''), ';'), v.typology) AS documented_target
FROM visible_attempts v
CROSS JOIN rules_implemented r
LEFT JOIN detections d ON d.attempt_id = v.attempt_id AND d.rule_id = r.rule_id AND d.ruleset = 'implemented'
GROUP BY v.typology, r.rule_id
ORDER BY v.typology, r.rule_id;

-- name: typology_coverage
SELECT v.typology, count(*) AS visible_attempts,
       count(*) FILTER (WHERE v.attempt_id IN (SELECT attempt_id FROM detections WHERE ruleset = 'implemented')) AS detected_attempts,
       count(*) FILTER (WHERE v.attempt_id IN (SELECT attempt_id FROM detections WHERE ruleset = 'implemented')) / count(*) AS detection_rate,
       (SELECT string_agg(rule_id, ', ' ORDER BY rule_id) FROM rules_implemented r
         WHERE list_contains(string_split(replace(r.typology, ' ', ''), ';'), v.typology)) AS rules_designed_for_it
FROM visible_attempts v GROUP BY 1 ORDER BY detection_rate;

-- name: coverage_summary
SELECT count(*) AS visible_attempts,
       count(*) FILTER (WHERE attempt_id IN (SELECT attempt_id FROM detections WHERE ruleset = 'implemented')) AS detected_attempts,
       count(*) FILTER (WHERE attempt_id IN (SELECT attempt_id FROM detections WHERE ruleset = 'implemented')) / count(*) AS coverage,
       count(DISTINCT typology) AS typologies,
       count(DISTINCT typology) FILTER (WHERE typology IN (
           SELECT DISTINCT unnest(string_split(replace(typology, ' ', ''), ';')) FROM rules_implemented)) AS typologies_with_a_designed_rule
FROM visible_attempts;
