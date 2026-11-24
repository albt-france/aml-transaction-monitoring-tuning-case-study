-- A spike that should NOT be escalated: corporate alerts on Wednesday 14 September 2022.
-- Baseline = mean corporate alerts per day on the other Tuesdays to Thursdays of the window, first day excluded
-- (its self-transfer batch is a separate issue, see sql/04).

CREATE OR REPLACE TABLE corp_daily AS
SELECT a.day, count(*) AS corporate_alerts, count(*) FILTER (WHERE a.payroll_driven) AS payroll_driven_alerts
FROM alerts a JOIN customers c USING (customer_id)
WHERE c.segment = 'corporate' GROUP BY 1;

CREATE OR REPLACE TABLE corp_baseline AS
SELECT avg(corporate_alerts) AS baseline FROM corp_daily
WHERE dayofweek(day) IN (2, 3, 4) AND day NOT IN ((SELECT d0 FROM period), DATE '2022-09-14');

-- name: payroll_corporate_daily
SELECT day, dayname(day) AS weekday, corporate_alerts, payroll_driven_alerts, (SELECT baseline FROM corp_baseline) AS baseline
FROM corp_daily ORDER BY day;

-- name: payroll_spike_breakdown
SELECT a.rule_id, a.payroll_driven, count(*) AS alerts,
       count(*) FILTER (WHERE c.known_payroll) AS on_known_payroll_customers,
       sum(a.is_tp) AS true_positives,
       count(*) FILTER (WHERE d.decision <> 'closed_no_issue') AS escalated_or_sar
FROM alerts a JOIN customers c USING (customer_id) JOIN dispositions d USING (alert_id)
WHERE c.segment = 'corporate' AND a.day = DATE '2022-09-14'
GROUP BY 1, 2 ORDER BY 1, 2;

-- name: payroll_verdict
WITH s AS (SELECT * FROM corp_daily WHERE day = DATE '2022-09-14'),
     pay AS (SELECT count(*) AS payments, count(DISTINCT account_ref) AS paying_accounts,
                    median(amount_paid) AS median_salary_eur
             FROM read_parquet('{SIM}/payroll_batch.parquet')),
     pd AS (SELECT a.*, c.known_payroll, d.decision FROM alerts a JOIN customers c USING (customer_id)
            JOIN dispositions d USING (alert_id) WHERE a.day = DATE '2022-09-14' AND a.payroll_driven)
SELECT s.corporate_alerts, (SELECT baseline FROM corp_baseline) AS baseline,
       s.corporate_alerts / (SELECT baseline FROM corp_baseline) - 1 AS spike,
       s.payroll_driven_alerts,
       (SELECT avg(CASE WHEN known_payroll THEN 1 ELSE 0 END) FROM pd) AS share_known_payroll,
       (SELECT coalesce(sum(is_tp), 0) FROM pd) AS laundering_hits,
       (SELECT count(*) FILTER (WHERE decision <> 'closed_no_issue') FROM pd) AS escalated,
       pay.payments, pay.paying_accounts, pay.median_salary_eur,
       'Expected activity (KYC declares payroll): no risk increase, do not escalate; add a known-payroll exclusion and watch the next cycle' AS verdict
FROM s, pay;
