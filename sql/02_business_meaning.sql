-- What the fields mean for the business (IBM PUBLIC DATA, synthetic; Bank N feed SIMULATED wrapper).

-- name: bm_flow_types
SELECT CASE WHEN is_self THEN 'self-transfer (same account)'
            WHEN from_bank = to_bank THEN 'same bank, different account'
            WHEN to_bank IS NULL THEN 'beneficiary bank missing'
            ELSE 'between banks' END AS flow_type,
       count(*) AS n_rows, count(*) / sum(count(*)) OVER () AS share_rows,
       sum(is_laundering) AS laundering_rows,
       sum(is_laundering) / sum(sum(is_laundering)) OVER () AS share_of_laundering
FROM tx WHERE source = 'ibm' GROUP BY 1 ORDER BY n_rows DESC;

-- name: bm_format_meaning
SELECT payment_format,
       approx_quantile(amount_paid_usd, 0.5) AS median_usd,
       approx_quantile(amount_paid_usd, 0.99) AS p99_usd,
       avg(CASE WHEN payment_currency <> receiving_currency THEN 1 ELSE 0 END) AS share_cross_currency,
       avg(CASE WHEN from_bank <> to_bank THEN 1 ELSE 0 END) AS share_between_banks,
       avg(CASE WHEN is_self THEN 1 ELSE 0 END) AS share_self,
       avg(is_laundering) AS laundering_rate
FROM tx WHERE source = 'ibm' GROUP BY 1 ORDER BY 1;

-- name: bm_self_transfers_by_day
SELECT day, count(*) AS n_rows,
       count(*) FILTER (WHERE is_self) AS self_rows,
       count(*) FILTER (WHERE payment_format = 'Reinvestment') AS reinvestment_rows,
       count(*) FILTER (WHERE is_self) / count(*) AS share_self
FROM tx WHERE source = 'ibm' GROUP BY 1 ORDER BY 1;

-- name: bm_cross_currency
SELECT count(*) FILTER (WHERE payment_currency <> receiving_currency) AS cross_currency_rows,
       avg(CASE WHEN payment_currency <> receiving_currency THEN 1 ELSE 0 END) AS share_cross_currency,
       count(*) FILTER (WHERE payment_currency = receiving_currency AND abs(amount_paid - amount_received) > 0.01) AS same_currency_amount_mismatch
FROM tx WHERE source = 'ibm';

-- name: bm_bank_n_book
SELECT b.segment, count(DISTINCT b.customer_id) AS customers, count(*) AS accounts,
       count(*) FILTER (WHERE l.acct_key IS NOT NULL) AS laundering_accounts
FROM book b LEFT JOIN (SELECT DISTINCT acct_key FROM lab_ad) l USING (acct_key)
GROUP BY 1 ORDER BY 1;
