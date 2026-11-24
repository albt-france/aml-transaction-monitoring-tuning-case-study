-- Rule performance measured with the IBM labels (PUBLIC DATA, synthetic) on the SIMULATED Bank N rule set.
-- precision = true-positive alerts / alerts ; recall = laundering accounts with a true-positive alert from the rule
-- / all laundering accounts of the book. "Unique" = laundering accounts that no other implemented rule catches.

CREATE OR REPLACE TABLE laundering_accounts AS SELECT DISTINCT acct_key FROM lab_ad;

-- name: rule_performance
WITH a AS (
    SELECT 'documented' AS ruleset, * FROM alerts_documented
    UNION ALL SELECT 'implemented', * FROM alerts_implemented
),
tp_acc AS (SELECT DISTINCT ruleset, rule_id, acct_key FROM a WHERE is_tp = 1),
uniq AS (
    SELECT t.ruleset, t.rule_id, count(*) AS unique_tp_accounts
    FROM tp_acc t
    WHERE NOT EXISTS (SELECT 1 FROM tp_acc o WHERE o.ruleset = t.ruleset AND o.acct_key = t.acct_key AND o.rule_id <> t.rule_id)
    GROUP BY 1, 2
),
r AS (SELECT 'documented' AS ruleset, rule_id, name FROM rules_documented
      UNION ALL SELECT 'implemented', rule_id, name FROM rules_implemented)
SELECT r.ruleset, r.rule_id, r.name,
       count(a.rule_id) AS alerts,
       count(a.rule_id) / sum(count(a.rule_id)) OVER (PARTITION BY r.ruleset) AS share_of_alerts,
       coalesce(sum(a.is_tp), 0) AS tp_alerts,
       coalesce(sum(a.is_tp), 0) / nullif(count(a.rule_id), 0) AS precision,
       (SELECT count(*) FROM tp_acc t WHERE t.ruleset = r.ruleset AND t.rule_id = r.rule_id) AS tp_accounts,
       (SELECT count(*) FROM tp_acc t WHERE t.ruleset = r.ruleset AND t.rule_id = r.rule_id)
           / (SELECT count(*) FROM laundering_accounts) AS recall,
       coalesce(any_value(u.unique_tp_accounts), 0) AS unique_tp_accounts,
       count(a.rule_id) * 7.0 / (SELECT n_days FROM period) AS alerts_per_week
FROM r
LEFT JOIN a ON a.ruleset = r.ruleset AND a.rule_id = r.rule_id
LEFT JOIN uniq u ON u.ruleset = r.ruleset AND u.rule_id = r.rule_id
GROUP BY r.ruleset, r.rule_id, r.name
ORDER BY r.ruleset, r.rule_id;

-- name: system_summary
WITH a AS (SELECT 'documented' AS ruleset, * FROM alerts_documented UNION ALL SELECT 'implemented', * FROM alerts_implemented)
SELECT ruleset, count(*) AS alerts, sum(is_tp) AS tp_alerts, avg(is_tp) AS precision,
       count(DISTINCT acct_key) AS alerted_accounts,
       count(DISTINCT acct_key) FILTER (WHERE is_tp = 1) AS tp_accounts,
       count(DISTINCT acct_key) FILTER (WHERE is_tp = 1) / (SELECT count(*) FROM laundering_accounts) AS recall,
       (SELECT count(*) FROM laundering_accounts) AS laundering_accounts,
       (SELECT count(*) FROM book) AS book_accounts,
       (SELECT count(*) FROM lab_ad) / (SELECT count(*) FROM ad_implemented) AS base_rate_account_days,
       count(*) * 7.0 / (SELECT n_days FROM period) AS alerts_per_week
FROM a GROUP BY 1 ORDER BY 1;

-- name: doc_vs_code
WITH d AS (SELECT rule_id, acct_key, day, is_tp FROM alerts_documented),
     i AS (SELECT rule_id, acct_key, day, is_tp FROM alerts_implemented)
SELECT r.rule_id, r.name,
       rd.basis AS documented_basis, ri.basis AS implemented_basis,
       rd.exclude_self AS documented_excludes_self, ri.exclude_self AS implemented_excludes_self,
       rd.lookback_days AS documented_lookback, ri.lookback_days AS implemented_lookback,
       (SELECT count(*) FROM d WHERE d.rule_id = r.rule_id) AS alerts_documented,
       (SELECT count(*) FROM i WHERE i.rule_id = r.rule_id) AS alerts_implemented,
       (SELECT count(*) FROM d JOIN i USING (rule_id, acct_key, day) WHERE d.rule_id = r.rule_id) AS alerts_in_both,
       (SELECT coalesce(sum(is_tp), 0) FROM d WHERE d.rule_id = r.rule_id) AS tp_documented,
       (SELECT coalesce(sum(is_tp), 0) FROM i WHERE i.rule_id = r.rule_id) AS tp_implemented,
       (SELECT count(*) FROM d WHERE d.rule_id = r.rule_id AND d.is_tp = 1
            AND NOT EXISTS (SELECT 1 FROM i WHERE i.rule_id = d.rule_id AND i.acct_key = d.acct_key AND i.is_tp = 1)) AS tp_accounts_missed_by_code,
       (rd.basis <> ri.basis OR rd.exclude_self <> ri.exclude_self OR rd.lookback_days <> ri.lookback_days) AS gap
FROM rules_documented r
JOIN rules_documented rd USING (rule_id)
JOIN rules_implemented ri USING (rule_id)
ORDER BY r.rule_id;

-- name: r04_self_transfer_effect
-- Implemented R04 alerts that do not exist when self-transfers are excluded, as documented.
SELECT count(*) AS r04_alerts_implemented,
       count(*) FILTER (WHERE d.acct_key IS NULL) AS alerts_only_because_of_self_transfers,
       count(*) FILTER (WHERE d.acct_key IS NULL) / count(*) AS share_without_business_meaning,
       count(*) FILTER (WHERE d.acct_key IS NULL AND i.day = (SELECT d0 FROM period)) AS of_which_on_first_day,
       sum(i.is_tp) FILTER (WHERE d.acct_key IS NULL) AS tp_among_them
FROM alerts_implemented i
LEFT JOIN alerts_documented d ON d.rule_id = i.rule_id AND d.acct_key = i.acct_key AND d.day = i.day
WHERE i.rule_id = 'R04';

-- name: r02_currency_effect
-- R02 coded on raw amounts: which payment currencies its alerts come from, documented vs implemented.
WITH s AS (
    SELECT from_key AS acct_key, day, payment_currency,
           (amount_paid_usd >= 8000 AND amount_paid_usd < 10000) AS in_usd_band,
           (amount_paid >= 8000 AND amount_paid < 10000) AS in_raw_band, is_laundering
    FROM tx_book WHERE from_in_book AND NOT is_self
)
SELECT payment_currency,
       count(*) FILTER (WHERE in_usd_band) AS tx_in_documented_band,
       count(*) FILTER (WHERE in_raw_band) AS tx_in_coded_band,
       count(*) FILTER (WHERE in_usd_band AND NOT in_raw_band) AS tx_missed_by_code,
       sum(is_laundering) FILTER (WHERE in_usd_band AND NOT in_raw_band) AS laundering_tx_missed_by_code,
       count(*) FILTER (WHERE in_raw_band AND NOT in_usd_band) AS tx_added_by_code
FROM s GROUP BY 1 HAVING count(*) FILTER (WHERE in_usd_band OR in_raw_band) > 0
ORDER BY tx_missed_by_code DESC;

-- name: feed_defect_impact
-- Rows that lost the beneficiary bank (SIMULATED ACH feed defect) and what R07 cannot see because of it.
-- The account number survives in the key, so the lost bank can be recovered here for measurement only.
WITH lost AS (
    SELECT t.*, split_part(t.to_key, '|', 1) AS true_bank FROM tx_book t WHERE t.to_bank IS NULL AND t.from_in_book
),
r07_blind AS (
    SELECT DISTINCT l.from_key AS acct_key, l.day
    FROM lost l JOIN bank_country b ON b.bank = l.true_bank JOIN corridor_tier c USING (bank_country)
    WHERE c.corridor_tier = 'high' AND l.amount_paid_usd >= (SELECT threshold FROM rules_implemented WHERE rule_id = 'R07')
      AND NOT EXISTS (SELECT 1 FROM alerts_implemented a WHERE a.rule_id = 'R07' AND a.acct_key = l.from_key AND a.day = l.day)
)
SELECT (SELECT count(*) FROM lost) AS book_rows_without_beneficiary_bank,
       (SELECT sum(is_laundering) FROM lost) AS laundering_rows_among_them,
       (SELECT count(*) FROM r07_blind) AS r07_alerts_missed,
       (SELECT count(*) FROM r07_blind b JOIN lab_ad l USING (acct_key, day)) AS r07_missed_on_laundering_account_days,
       (SELECT min(day) FROM lost) AS first_day;
