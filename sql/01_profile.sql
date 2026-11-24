-- Profile of the IBM transactions (PUBLIC DATA, synthetic AML benchmark) and of the analysis window.

-- name: profile_overview
SELECT (SELECT count(*) FROM tx_raw)                                              AS rows_in_file,
       (SELECT sum(n_rows) FROM daily_volume WHERE day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period)) AS rows_in_window,
       (SELECT sum(n_rows) FROM daily_volume WHERE day > (SELECT d1 FROM period)) AS rows_in_sparse_tail,
       (SELECT d0 FROM period) AS first_day, (SELECT d1 FROM period) AS last_complete_day,
       (SELECT max(day) FROM daily_volume) AS last_day_in_file,
       (SELECT n_days FROM period) AS complete_days,
       (SELECT sum(is_laundering) FROM tx_raw) AS laundering_rows,
       (SELECT avg(is_laundering) FROM tx_raw) AS laundering_rate,
       (SELECT count(*) FROM accounts) AS accounts_in_master,
       (SELECT count(DISTINCT entity_id) FROM accounts) AS entities_in_master,
       (SELECT count(*) FROM book) AS bank_n_accounts,
       (SELECT count(DISTINCT customer_id) FROM book) AS bank_n_customers,
       (SELECT count(*) FROM tx_book) AS bank_n_rows,
       (SELECT count(DISTINCT acct_key) FROM lab_ad) AS bank_n_laundering_accounts;

-- name: profile_daily
SELECT day, n_rows, n_laundering,
       day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period) AS in_window
FROM daily_volume ORDER BY day;

-- name: profile_formats
SELECT payment_format, count(*) AS n_rows, count(*) / sum(count(*)) OVER () AS share_rows,
       sum(is_laundering) AS laundering_rows, avg(is_laundering) AS laundering_rate,
       sum(is_laundering) / sum(sum(is_laundering)) OVER () AS share_of_laundering
FROM tx WHERE source = 'ibm' GROUP BY 1 ORDER BY n_rows DESC;

-- name: profile_currencies
SELECT payment_currency, count(*) AS n_rows, count(*) / sum(count(*)) OVER () AS share_rows,
       avg(is_laundering) AS laundering_rate
FROM tx WHERE source = 'ibm' GROUP BY 1 ORDER BY n_rows DESC;
