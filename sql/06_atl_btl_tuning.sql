-- Threshold tuning with above-the-line / below-the-line testing (ATL/BTL) on the IMPLEMENTED one-day rules.
-- For each rule the threshold is moved from 0.5x to 20x its current value:
--   below the line (multiplier < 1): how many more alerts and true positives a lower threshold would bring;
--   above the line (multiplier > 1): how many alerts disappear and which true positives would be lost.
-- "lost_unique" = laundering accounts caught at the current threshold, lost at the new one, and caught by no other
-- implemented rule: the true cost of raising the threshold.

CREATE OR REPLACE TABLE tune_metric AS
WITH m AS (
    SELECT 'R01' AS rule_id, acct_key, day, out_max_usd AS metric FROM ad_implemented WHERE out_max_usd IS NOT NULL
    UNION ALL SELECT 'R03', acct_key, day, out_cp FROM ad_implemented WHERE out_cp > 0
    UNION ALL SELECT 'R06', acct_key, day, in_cp FROM ad_implemented WHERE in_cp > 0
    UNION ALL SELECT 'R07', acct_key, day, hr_max_usd FROM ad_implemented WHERE hr_max_usd IS NOT NULL
    UNION ALL SELECT 'R09', acct_key, day, round_max_usd FROM ad_implemented WHERE round_max_usd IS NOT NULL
    UNION ALL SELECT 'R11', acct_key, day, out_max_usd FROM ad_implemented WHERE risk_rating = 'high' AND out_max_usd IS NOT NULL
)
SELECT m.*, r.threshold, (l.acct_key IS NOT NULL) AS is_tp
FROM m JOIN rules_implemented r USING (rule_id)
LEFT JOIN lab_ad l ON l.acct_key = m.acct_key AND l.day = m.day
WHERE m.metric >= 0.5 * r.threshold;

CREATE OR REPLACE TABLE multipliers AS
SELECT unnest([0.5, 0.75, 1, 1.5, 2, 3, 5, 10, 20]) AS mult;

CREATE OR REPLACE TABLE tp_other_rules AS
SELECT DISTINCT r.rule_id AS excluded_rule, a.acct_key
FROM rules_implemented r
JOIN alerts_implemented a ON a.rule_id <> r.rule_id AND a.is_tp = 1;

-- name: atl_btl_curve
WITH base AS (SELECT DISTINCT rule_id, acct_key FROM tune_metric WHERE is_tp AND metric >= threshold),
g AS (
    SELECT t.rule_id, x.mult, any_value(t.threshold) * x.mult AS threshold,
           count(*) AS alerts, sum(CASE WHEN t.is_tp THEN 1 ELSE 0 END) AS tp_alerts,
           count(DISTINCT t.acct_key) FILTER (WHERE t.is_tp) AS tp_accounts,
           list(DISTINCT t.acct_key) FILTER (WHERE t.is_tp) AS tp_list
    FROM tune_metric t JOIN multipliers x ON t.metric >= t.threshold * x.mult
    GROUP BY 1, 2
)
SELECT g.rule_id, g.mult, g.threshold, g.alerts, g.alerts * 7.0 / (SELECT n_days FROM period) AS alerts_per_week,
       g.tp_alerts, g.tp_accounts, g.tp_alerts / g.alerts AS precision,
       (SELECT count(*) FROM base b WHERE b.rule_id = g.rule_id AND NOT list_contains(coalesce(g.tp_list, []), b.acct_key)) AS lost_tp_accounts,
       (SELECT count(*) FROM base b WHERE b.rule_id = g.rule_id AND NOT list_contains(coalesce(g.tp_list, []), b.acct_key)
            AND b.acct_key NOT IN (SELECT acct_key FROM tp_other_rules o WHERE o.excluded_rule = g.rule_id)) AS lost_unique_tp_accounts
FROM g ORDER BY g.rule_id, g.mult;

-- The tuned scenario (alerts_tuned) is produced by sql/03 run on rules_tuned = documented code (fixes R02, R04,
-- R10) + the thresholds in tuning_proposal (built by src/run_sql.py from this curve). The known-payroll exclusion
-- for R05 is applied here.
DELETE FROM alerts_tuned WHERE rule_id = 'R05' AND payroll_driven;

-- name: tuning_proposal_impact
WITH cur AS (SELECT rule_id, count(*) AS alerts_now, sum(is_tp) AS tp_now FROM alerts_implemented GROUP BY 1),
     new AS (SELECT rule_id, count(*) AS alerts_after, sum(is_tp) AS tp_after FROM alerts_tuned GROUP BY 1),
     acc_now AS (SELECT DISTINCT acct_key FROM alerts_implemented WHERE is_tp = 1),
     acc_new AS (SELECT DISTINCT acct_key FROM alerts_tuned WHERE is_tp = 1)
SELECT r.rule_id, r.name, coalesce(p.action, 'keep') AS action, p.current_threshold, p.proposed_threshold, p.rationale,
       coalesce(cur.alerts_now, 0) AS alerts_now, coalesce(new.alerts_after, 0) AS alerts_after,
       coalesce(new.alerts_after, 0) / nullif(cur.alerts_now, 0) - 1 AS change_in_alerts,
       coalesce(cur.tp_now, 0) AS tp_alerts_now, coalesce(new.tp_after, 0) AS tp_alerts_after
FROM rules_implemented r
LEFT JOIN tuning_proposal p USING (rule_id)
LEFT JOIN cur USING (rule_id) LEFT JOIN new USING (rule_id)
ORDER BY r.rule_id;

-- name: tuning_summary
SELECT (SELECT count(*) FROM alerts_implemented) AS alerts_now,
       (SELECT count(*) FROM alerts_tuned) AS alerts_after,
       (SELECT count(*) FROM alerts_tuned) / (SELECT count(*) FROM alerts_implemented) - 1 AS change_in_alerts,
       (SELECT avg(is_tp) FROM alerts_implemented) AS precision_now,
       (SELECT avg(is_tp) FROM alerts_tuned) AS precision_after,
       (SELECT count(DISTINCT acct_key) FROM alerts_implemented WHERE is_tp = 1) AS tp_accounts_now,
       (SELECT count(DISTINCT acct_key) FROM alerts_tuned WHERE is_tp = 1) AS tp_accounts_after,
       (SELECT count(*) FROM (SELECT DISTINCT acct_key FROM alerts_implemented WHERE is_tp = 1
                               EXCEPT SELECT DISTINCT acct_key FROM alerts_tuned WHERE is_tp = 1)) AS tp_accounts_lost,
       (SELECT count(*) FROM (SELECT DISTINCT acct_key FROM alerts_tuned WHERE is_tp = 1
                               EXCEPT SELECT DISTINCT acct_key FROM alerts_implemented WHERE is_tp = 1)) AS tp_accounts_gained;
