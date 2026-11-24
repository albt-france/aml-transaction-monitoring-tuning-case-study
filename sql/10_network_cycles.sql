-- New network scenario R13 (proposal), built for the two typologies no rule targets: CYCLE and SCATTER-GATHER.
-- Runs on the Bank N feed (IBM PUBLIC DATA, synthetic). Bounded so it stays cheap on 32M rows:
--   cycle          : time-ordered path that returns to a Bank N account, 2 to 12 hops, each hop within 3.5 days of
--                    the previous one and the whole loop within 7 days, each hop moving 80%-115% of the previous
--                    USD amount (funds passed on minus fees, plus FX noise), no account visited twice;
--   scatter-gather : one account pays 3+ distinct intermediaries that each pass 85%-100% of the amount on to the
--                    same final account within 5 days; alert on the Bank N side (origin and/or final account).
-- Parameters follow the typology definitions (pass-through with fees). They were checked against the structure of
-- the IBM Patterns file (hop timing, amount drift), so the recall measured here is optimistic: see the model note.

CREATE OR REPLACE TABLE edges AS
SELECT t.from_key, t.to_key, t.ts, t.amount_paid_usd AS usd,
       t.from_key IN (SELECT acct_key FROM book) AS from_in_book,
       t.to_key IN (SELECT acct_key FROM book) AS to_in_book
FROM tx t WHERE NOT t.is_self AND t.amount_paid_usd > 0;

CREATE OR REPLACE TABLE cycles AS
WITH RECURSIVE walk(start_key, cur_key, start_ts, last_ts, last_usd, hops, path) AS (
    SELECT from_key, to_key, ts, ts, usd, 1, [from_key, to_key]
    FROM edges WHERE from_in_book AND usd >= 1000
    UNION ALL
    SELECT w.start_key, e.to_key, w.start_ts, e.ts, e.usd, w.hops + 1, list_append(w.path, e.to_key)
    FROM walk w
    JOIN edges e ON e.from_key = w.cur_key
    WHERE w.cur_key <> w.start_key
      AND w.hops < 12
      AND e.ts > w.last_ts AND e.ts <= w.last_ts + INTERVAL 84 HOUR AND e.ts <= w.start_ts + INTERVAL 7 DAY
      AND e.usd BETWEEN 0.80 * w.last_usd AND 1.15 * w.last_usd
      AND (e.to_key = w.start_key OR NOT list_contains(w.path, e.to_key))
)
SELECT start_key AS acct_key, CAST(last_ts AS DATE) AS day, hops, path
FROM walk WHERE cur_key = start_key AND hops >= 2;

CREATE OR REPLACE TABLE scatter_gather AS
WITH pairs AS (
    SELECT e1.from_key AS origin, e1.to_key AS mid, e2.to_key AS final, e2.ts AS ts2,
           e1.from_in_book AS origin_in_book, e2.to_in_book AS final_in_book
    FROM edges e1 JOIN edges e2 ON e2.from_key = e1.to_key
    WHERE (e1.from_in_book OR e2.to_in_book)
      AND e1.usd >= 1000
      AND e2.to_key NOT IN (e1.from_key, e1.to_key) AND e1.to_key <> e1.from_key
      AND e2.ts > e1.ts AND e2.ts <= e1.ts + INTERVAL 5 DAY
      AND e2.usd BETWEEN 0.85 * e1.usd AND 1.0 * e1.usd
)
SELECT origin, final, count(DISTINCT mid) AS intermediaries, CAST(max(ts2) AS DATE) AS day,
       bool_or(origin_in_book) AS origin_in_book, bool_or(final_in_book) AS final_in_book
FROM pairs GROUP BY origin, final HAVING count(DISTINCT mid) >= 3;

CREATE OR REPLACE TABLE alerts_network AS
WITH raw AS (
    SELECT acct_key, day, 'cycle' AS pattern FROM cycles
    UNION ALL SELECT origin, day, 'scatter-gather' FROM scatter_gather WHERE origin_in_book
    UNION ALL SELECT final, day, 'scatter-gather' FROM scatter_gather WHERE final_in_book
),
d AS (SELECT acct_key, day, string_agg(DISTINCT pattern, '+') AS pattern FROM raw GROUP BY 1, 2),
s AS (SELECT *, day - lag(day) OVER (PARTITION BY acct_key ORDER BY day) AS gap FROM d)
SELECT 'R13' AS rule_id, s.acct_key, s.day, s.pattern,
       CAST(EXISTS (SELECT 1 FROM lab_ad l WHERE l.acct_key = s.acct_key AND l.day BETWEEN s.day - 6 AND s.day) AS INTEGER) AS is_tp,
       CAST(floor(datediff('day', (SELECT d0 FROM period), s.day) / 7) + 1 AS INTEGER) AS wk
FROM s WHERE s.gap IS NULL OR s.gap >= 7;

CREATE OR REPLACE TABLE detections_network AS
SELECT DISTINCT v.attempt_id
FROM visible_attempts v
JOIN attempt_book_accounts ab USING (attempt_id)
JOIN alerts_network a ON a.acct_key = ab.acct_key AND a.is_tp = 1 AND a.day BETWEEN v.d_start AND v.d_end + 2;

-- name: network_scenario_performance
SELECT pattern, count(*) AS alerts, sum(is_tp) AS tp_alerts, avg(is_tp) AS precision,
       count(DISTINCT acct_key) FILTER (WHERE is_tp = 1) AS tp_accounts,
       count(DISTINCT acct_key) FILTER (WHERE is_tp = 1
           AND acct_key NOT IN (SELECT acct_key FROM alerts_tuned WHERE is_tp = 1)) AS tp_accounts_new_vs_tuned_rules,
       count(*) * 7.0 / (SELECT n_days FROM period) AS alerts_per_week
FROM (SELECT * FROM alerts_network UNION ALL SELECT rule_id, acct_key, day, 'all R13', is_tp, wk FROM alerts_network)
GROUP BY 1 ORDER BY 1;

-- name: network_typology_coverage
SELECT v.typology, count(*) AS visible_attempts,
       avg(CASE WHEN v.attempt_id IN (SELECT attempt_id FROM detections WHERE ruleset = 'implemented') THEN 1 ELSE 0 END) AS rules_now,
       avg(CASE WHEN v.attempt_id IN (SELECT attempt_id FROM detected_by('alerts_tuned')) THEN 1 ELSE 0 END) AS tuned_rules,
       avg(CASE WHEN v.attempt_id IN (SELECT attempt_id FROM detections_network) THEN 1 ELSE 0 END) AS r13_alone,
       avg(CASE WHEN v.attempt_id IN (SELECT attempt_id FROM detected_by('alerts_tuned'))
                  OR v.attempt_id IN (SELECT attempt_id FROM detections_network) THEN 1 ELSE 0 END) AS tuned_rules_plus_r13
FROM visible_attempts v GROUP BY 1 ORDER BY 1;

-- name: network_cycle_lengths
SELECT hops, count(*) AS cycles FROM cycles GROUP BY 1 ORDER BY 1;
