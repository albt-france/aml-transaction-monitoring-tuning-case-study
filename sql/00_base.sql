-- Base layer on the IBM Parquet files (PUBLIC DATA, synthetic AML benchmark, AMLSim).
-- Account keys are 'bank|account' with the bank code cast to an integer, so '020' and '20' match the accounts file.

CREATE OR REPLACE VIEW tx_raw AS
SELECT * REPLACE (CAST(day AS DATE) AS day)
FROM read_parquet('{PARQ}/trans/**/*.parquet', hive_partitioning = true);

CREATE OR REPLACE TABLE daily_volume AS
SELECT day, count(*) AS n_rows, sum(is_laundering) AS n_laundering FROM tx_raw GROUP BY day;

-- Complete days only: the file ends with a sparse tail of late rows (a few thousand per day at most).
CREATE OR REPLACE TABLE period AS
SELECT min(day) AS d0, max(day) AS d1, count(*) AS n_days
FROM daily_volume
WHERE n_rows >= 0.2 * (SELECT median(n_rows) FROM daily_volume);

CREATE OR REPLACE TABLE accounts AS
SELECT CAST(CAST(bank_id AS BIGINT) AS VARCHAR) || '|' || account AS acct_key,
       CAST(CAST(bank_id AS BIGINT) AS VARCHAR) AS bank,
       entity_id,
       CASE WHEN bank_country IN ('Savings', 'First', 'National') THEN 'Unspecified'
            WHEN bank_country = 'Crytpo' THEN 'Crypto platform'
            ELSE bank_country END AS bank_country
FROM read_parquet('{PARQ}/accounts.parquet');

CREATE OR REPLACE TABLE bank_country AS
SELECT bank, any_value(bank_country) AS bank_country FROM accounts GROUP BY bank;
