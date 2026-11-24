-- "Bank N" transaction feed (SIMULATED wrapper around PUBLIC DATA, synthetic):
--   * IBM rows of the complete-day window
--   * plus the SIMULATED mid-month payroll batches of a few corporate customers (data/sim/payroll_batch.parquet)
--   * with the SIMULATED feed defect applied: from {DEFECT_START}, part of the {DEFECT_FORMAT} rows arrive
--     without the counterparty (beneficiary) bank. The account number survives, so the account key is kept.

CREATE OR REPLACE TABLE tx AS
WITH ibm AS (
    SELECT ts, day,
           CAST(CAST(from_bank AS BIGINT) AS VARCHAR) AS from_bank, from_account,
           CAST(CAST(to_bank AS BIGINT) AS VARCHAR) AS to_bank, to_account,
           amount_paid, payment_currency, amount_received, receiving_currency, payment_format,
           is_laundering, amount_paid_usd, amount_received_usd, 'ibm' AS source
    FROM tx_raw
    WHERE day BETWEEN (SELECT d0 FROM period) AND (SELECT d1 FROM period)
),
payroll AS (
    SELECT p.ts, CAST(p.ts AS DATE) AS day,
           split_part(m.acct_key, '|', 1), split_part(m.acct_key, '|', 2), '999999', p.employee_ref,
           p.amount_paid, p.payment_currency, p.amount_paid, p.payment_currency, 'ACH',
           CAST(0 AS TINYINT), p.amount_paid_usd, p.amount_paid_usd, 'payroll_sim'
    FROM read_parquet('{SIM}/payroll_batch.parquet') p
    JOIN id_accounts m USING (account_ref)
),
u AS (SELECT * FROM ibm UNION ALL SELECT * FROM payroll)
SELECT u.* REPLACE (
           CASE WHEN payment_format = '{DEFECT_FORMAT}' AND day >= DATE '{DEFECT_START}'
                     AND md5_number(concat_ws('|', ts, from_account, to_account, amount_paid)) % 10000 < {DEFECT_BP}
                THEN NULL ELSE to_bank END AS to_bank),
       from_bank || '|' || from_account AS from_key,
       to_bank || '|' || to_account AS to_key,
       (from_bank = to_bank AND from_account = to_account) AS is_self,
       CAST(floor(datediff('day', (SELECT d0 FROM period), day) / 7) + 1 AS INTEGER) AS wk
FROM u;

-- Rows that touch Bank N's book (either side); every rule and the model run on this subset.
CREATE OR REPLACE TABLE tx_book AS
SELECT t.*, (fb.acct_key IS NOT NULL) AS from_in_book, (tb.acct_key IS NOT NULL) AS to_in_book
FROM tx t
LEFT JOIN book fb ON fb.acct_key = t.from_key
LEFT JOIN book tb ON tb.acct_key = t.to_key
WHERE fb.acct_key IS NOT NULL OR tb.acct_key IS NOT NULL;

-- laundering involvement per account and day (truth from the IBM labels, book accounts only)
CREATE OR REPLACE TABLE lab_ad AS
SELECT acct_key, day, count(*) AS n_laundering FROM (
    SELECT from_key AS acct_key, day FROM tx_book WHERE is_laundering = 1 AND from_in_book
    UNION ALL SELECT to_key, day FROM tx_book WHERE is_laundering = 1 AND to_in_book) GROUP BY 1, 2;

