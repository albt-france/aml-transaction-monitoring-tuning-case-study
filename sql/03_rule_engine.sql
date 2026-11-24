-- The 12 Bank N rules (SIMULATED rule set) run on the Bank N feed (IBM PUBLIC DATA, synthetic + SIMULATED layer).
-- This file is executed twice by src/run_sql.py: {RULESET} = documented, then {RULESET} = implemented.
-- Every parameter is read from rules_{RULESET}, so a difference between documentation and code shows up as a
-- difference in the alerts, not as a hidden edit in the SQL.
-- Alert unit: (rule, account, day). An alert is a true positive (is_tp) when the account sent or received a
-- transaction labelled Is Laundering = 1 inside the rule's lookback window ending on the alert day.
-- Re-alerting on the same account is suppressed for lookback_days after an alert.

CREATE OR REPLACE MACRO thr(r) AS (SELECT threshold FROM rules_{RULESET} WHERE rule_id = r);
CREATE OR REPLACE MACRO lb(r) AS (SELECT lookback_days FROM rules_{RULESET} WHERE rule_id = r);
CREATE OR REPLACE MACRO usd_basis(r) AS (SELECT basis = 'usd' FROM rules_{RULESET} WHERE rule_id = r);
CREATE OR REPLACE MACRO no_self(r) AS (SELECT exclude_self FROM rules_{RULESET} WHERE rule_id = r);

CREATE OR REPLACE TABLE ad_{RULESET} AS
WITH t AS (
    SELECT tb.*, coalesce(ct_to.corridor_tier, 'unknown') AS to_tier, coalesce(ct_from.corridor_tier, 'unknown') AS from_tier
    FROM tx_book tb
    LEFT JOIN bank_country bt ON bt.bank = tb.to_bank
    LEFT JOIN corridor_tier ct_to ON ct_to.bank_country = bt.bank_country
    LEFT JOIN bank_country bf ON bf.bank = tb.from_bank
    LEFT JOIN corridor_tier ct_from ON ct_from.bank_country = bf.bank_country
),
o AS (
    SELECT from_key AS acct_key, day,
           count(*) FILTER (WHERE NOT is_self)                                          AS out_cnt,
           sum(amount_paid_usd) FILTER (WHERE NOT is_self)                              AS out_usd,
           sum(amount_paid_usd)                                                         AS out_usd_all,
           count(DISTINCT to_key) FILTER (WHERE NOT is_self)                            AS out_cp,
           max(amount_paid_usd) FILTER (WHERE NOT is_self)                              AS out_max_usd,
           count(*) FILTER (WHERE NOT is_self AND amount_paid_usd >= 8000 AND amount_paid_usd < 10000) AS struct_usd_cnt,
           count(*) FILTER (WHERE NOT is_self AND amount_paid >= 8000 AND amount_paid < 10000)         AS struct_raw_cnt,
           max(amount_paid_usd) FILTER (WHERE NOT is_self AND amount_paid = round(amount_paid))        AS round_max_usd,
           max(amount_paid_usd) FILTER (WHERE NOT is_self AND (payment_format = 'Bitcoin'
                                         OR payment_currency <> receiving_currency))                AS conv_max_usd,
           coalesce(sum(amount_paid_usd) FILTER (WHERE payment_format = 'Cash'), 0)     AS cash_out_usd,
           max(amount_paid_usd) FILTER (WHERE NOT is_self AND to_tier = 'high')        AS hr_out_max_usd,
           count(*) FILTER (WHERE source = 'payroll_sim')                               AS payroll_cnt
    FROM t WHERE from_in_book GROUP BY 1, 2
),
i AS (
    SELECT to_key AS acct_key, day,
           sum(amount_received_usd) FILTER (WHERE NOT is_self)                          AS in_usd,
           sum(amount_received_usd)                                                     AS in_usd_all,
           count(DISTINCT from_key) FILTER (WHERE NOT is_self)                          AS in_cp,
           coalesce(sum(amount_received_usd) FILTER (WHERE payment_format = 'Cash'), 0) AS cash_in_usd,
           max(amount_received_usd) FILTER (WHERE NOT is_self AND from_tier = 'high')  AS hr_in_max_usd
    FROM t WHERE to_in_book GROUP BY 1, 2
)
SELECT acct_key, day, b.risk_rating, b.expected_monthly_volume,
       coalesce(out_cnt, 0) AS out_cnt, coalesce(out_usd, 0) AS out_usd, coalesce(out_usd_all, 0) AS out_usd_all,
       coalesce(out_cp, 0) AS out_cp, out_max_usd, coalesce(struct_usd_cnt, 0) AS struct_usd_cnt,
       coalesce(struct_raw_cnt, 0) AS struct_raw_cnt, round_max_usd, conv_max_usd,
       coalesce(cash_out_usd, 0) + coalesce(cash_in_usd, 0) AS cash_usd, greatest(hr_out_max_usd, hr_in_max_usd) AS hr_max_usd,
       coalesce(in_usd, 0) AS in_usd, coalesce(in_usd_all, 0) AS in_usd_all, coalesce(in_cp, 0) AS in_cp,
       coalesce(payroll_cnt, 0) AS payroll_cnt
FROM o FULL JOIN i USING (acct_key, day)
JOIN book b USING (acct_key);

CREATE OR REPLACE TABLE cand_{RULESET} AS
WITH w AS (
    SELECT *,
        sum(CASE WHEN usd_basis('R02') THEN struct_usd_cnt ELSE struct_raw_cnt END)
            OVER (PARTITION BY acct_key ORDER BY day RANGE BETWEEN INTERVAL (lb('R02') - 1) DAY PRECEDING AND CURRENT ROW) AS struct_win,
        CASE WHEN usd_basis('R02') THEN struct_usd_cnt ELSE struct_raw_cnt END AS struct_today,
        sum(CASE WHEN no_self('R04') THEN in_usd ELSE in_usd_all END)
            OVER (PARTITION BY acct_key ORDER BY day RANGE BETWEEN INTERVAL (lb('R04') - 1) DAY PRECEDING AND CURRENT ROW) AS in_win,
        sum(CASE WHEN no_self('R04') THEN out_usd ELSE out_usd_all END)
            OVER (PARTITION BY acct_key ORDER BY day RANGE BETWEEN INTERVAL (lb('R04') - 1) DAY PRECEDING AND CURRENT ROW) AS out_win,
        CASE WHEN no_self('R04') THEN out_usd ELSE out_usd_all END AS out_today_r04,
        sum(out_cnt) OVER (PARTITION BY acct_key ORDER BY day RANGE BETWEEN INTERVAL 7 DAY PRECEDING AND INTERVAL 1 DAY PRECEDING) AS prior_cnt,
        least(7, datediff('day', (SELECT d0 FROM period), day)) AS prior_days,
        sum(cash_usd) OVER (PARTITION BY acct_key ORDER BY day RANGE BETWEEN INTERVAL (lb('R10') - 1) DAY PRECEDING AND CURRENT ROW) AS cash_win,
        sum(out_usd) OVER (PARTITION BY acct_key ORDER BY day RANGE BETWEEN INTERVAL (lb('R12') - 1) DAY PRECEDING AND CURRENT ROW) AS out_7d
    FROM ad_{RULESET}
)
SELECT 'R01' AS rule_id, acct_key, day, out_max_usd AS metric, payroll_cnt FROM w WHERE out_max_usd >= thr('R01')
UNION ALL SELECT 'R02', acct_key, day, struct_win, payroll_cnt FROM w WHERE struct_today > 0 AND struct_win >= 3
UNION ALL SELECT 'R03', acct_key, day, out_cp, payroll_cnt FROM w WHERE out_cp >= thr('R03')
UNION ALL SELECT 'R04', acct_key, day, out_win / in_win, payroll_cnt FROM w
          WHERE out_today_r04 > 0 AND in_win >= thr('R04') AND out_win BETWEEN 0.8 * in_win AND 1.2 * in_win
UNION ALL SELECT 'R05', acct_key, day, out_cnt / (prior_cnt / prior_days), payroll_cnt FROM w
          WHERE prior_days >= 3 AND out_cnt >= 10 AND out_cnt >= thr('R05') * coalesce(prior_cnt, 0) / prior_days
UNION ALL SELECT 'R06', acct_key, day, in_cp, payroll_cnt FROM w WHERE in_cp >= thr('R06')
UNION ALL SELECT 'R07', acct_key, day, hr_max_usd, payroll_cnt FROM w WHERE hr_max_usd >= thr('R07')
UNION ALL SELECT 'R08', acct_key, day, conv_max_usd, payroll_cnt FROM w WHERE conv_max_usd >= thr('R08')
UNION ALL SELECT 'R09', acct_key, day, round_max_usd, payroll_cnt FROM w WHERE round_max_usd >= thr('R09')
UNION ALL SELECT 'R10', acct_key, day, cash_win, payroll_cnt FROM w WHERE cash_usd > 0 AND cash_win >= thr('R10')
UNION ALL SELECT 'R11', acct_key, day, out_max_usd, payroll_cnt FROM w WHERE risk_rating = 'high' AND out_max_usd >= thr('R11')
UNION ALL SELECT 'R12', acct_key, day, out_7d / (expected_monthly_volume * 7 / 30), payroll_cnt FROM w
          WHERE expected_monthly_volume IS NOT NULL AND out_usd > 0
            AND out_7d > thr('R12') * expected_monthly_volume * 7 / 30;

-- lab_ad (laundering involvement per account and day) is built in sql/00_bank_feed.sql

CREATE OR REPLACE TABLE alerts_{RULESET} AS
WITH s AS (
    SELECT c.*, r.lookback_days,
           day - lag(day) OVER (PARTITION BY c.rule_id, acct_key ORDER BY day) AS gap
    FROM cand_{RULESET} c JOIN rules_{RULESET} r USING (rule_id)
)
SELECT s.rule_id, s.acct_key, s.day, s.metric, (s.payroll_cnt > 0) AS payroll_driven,
       CAST(EXISTS (SELECT 1 FROM lab_ad l WHERE l.acct_key = s.acct_key
                    AND l.day BETWEEN s.day - CAST(s.lookback_days - 1 AS INTEGER) AND s.day) AS INTEGER) AS is_tp,
       CAST(floor(datediff('day', (SELECT d0 FROM period), s.day) / 7) + 1 AS INTEGER) AS wk
FROM s
WHERE s.gap IS NULL OR s.gap >= s.lookback_days;
